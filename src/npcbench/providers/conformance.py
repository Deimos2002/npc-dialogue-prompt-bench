"""Provider conformance fixtures: what every chat client must do (protocol; ADR 0002).

An adapter's tests build a client for each case (the fake by injecting a fault, a live
adapter by scripting its HTTP transport) and pass it to `check_stream`:

- `ok`: at least one visible text piece, then exactly one usage report as the final piece,
  with token counts that are None or non-negative, and a model version on some piece.
- `timeout`, `transport`, `truncation`, `malformed`: the stream raises `AttemptFailure` of
  the matching kind and nothing else. Only truncation may report usage first, because only
  then did the provider finish the response.
"""

from __future__ import annotations

from npcbench.providers.base import AttemptFailure, ChatClient, StreamPiece
from npcbench.schemas import ChatRequest, FailureKind

EXPECTED_FAILURE: dict[str, FailureKind | None] = {
    "ok": None,
    "timeout": "timeout",
    "transport": "transport",
    "truncation": "truncation",
    "malformed": "parse",
}
CASES = tuple(EXPECTED_FAILURE)


class ConformanceError(AssertionError):
    pass


def _check_usage(piece: StreamPiece) -> None:
    usage = piece.usage
    if usage is None:
        raise ConformanceError("ok: the final piece carries no usage")
    for count in (usage.input_tokens, usage.output_tokens):
        if count is not None and count < 0:
            raise ConformanceError(f"negative token count in usage {usage}")


def check_stream(client: ChatClient, request: ChatRequest, case: str) -> None:
    """Consume one stream and raise ConformanceError if it breaks the contract."""
    expected = EXPECTED_FAILURE[case]
    pieces: list[StreamPiece] = []
    try:
        for piece in client.stream(request):
            pieces.append(piece)
    except AttemptFailure as exc:
        if exc.kind != expected:
            raise ConformanceError(f"{case}: expected {expected!r}, got {exc.kind!r}") from exc
        if exc.kind != "truncation" and any(p.usage for p in pieces):
            raise ConformanceError(f"{case}: usage reported before a {exc.kind} failure") from exc
        return
    except Exception as exc:
        raise ConformanceError(
            f"{case}: failures must surface as AttemptFailure, not {type(exc).__name__}"
        ) from exc

    if expected is not None:
        raise ConformanceError(f"{case}: stream ended without the {expected!r} failure")
    if not any(p.text for p in pieces):
        raise ConformanceError("ok: no visible text")
    usage_at = [i for i, p in enumerate(pieces) if p.usage is not None]
    if usage_at != [len(pieces) - 1]:
        raise ConformanceError("ok: expected exactly one usage report, as the final piece")
    _check_usage(pieces[-1])
    if not any(p.model_version for p in pieces):
        raise ConformanceError("ok: no model version reported")
