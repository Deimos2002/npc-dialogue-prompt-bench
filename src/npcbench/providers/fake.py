"""Deterministic fake client and clock for tests and offline runs."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from npcbench.providers.base import AttemptFailure, StreamPiece
from npcbench.schemas import ChatRequest, FailureKind, Usage


class FakeClock:
    def __init__(self, start_ms: float = 0.0) -> None:
        self._now = start_ms

    def now_ms(self) -> float:
        return self._now

    def advance(self, ms: float) -> None:
        self._now += ms

    def sleep_ms(self, ms: float) -> None:
        self.advance(ms)


def echo_reply(request: ChatRequest) -> str:
    return f"Fake reply to: {request.messages[-1].content}"


@dataclass(frozen=True)
class Fault:
    """An injected attempt failure: `after_chunks` visible chunks, then `kind`.

    A timeout first waits `delay_ms`. Only truncation reports usage before failing, as a
    provider does when it stops at the output limit; `parse` stands for malformed output.
    """

    kind: FailureKind
    after_chunks: int = 0
    delay_ms: float = 0.0


Faults = Callable[[ChatRequest], Fault | None]


def fault_sequence(*faults: Fault | None) -> Faults:
    """Faults applied to successive streams in order; later streams run clean."""
    pending = list(faults)
    return lambda request: pending.pop(0) if pending else None


class FakeClient:
    """Streams a scripted reply word by word, advancing a fake clock between chunks."""

    def __init__(
        self,
        reply: Callable[[ChatRequest], str],
        clock: FakeClock,
        first_token_delay_ms: float = 0.0,
        chunk_delay_ms: float = 0.0,
        faults: Faults | None = None,
    ) -> None:
        self._reply = reply
        self._clock = clock
        self._first_token_delay_ms = first_token_delay_ms
        self._chunk_delay_ms = chunk_delay_ms
        self._faults = faults

    def stream(self, request: ChatRequest) -> Iterator[StreamPiece]:
        fault = self._faults(request) if self._faults else None
        chunks = re.findall(r"\S+\s*", self._reply(request))
        cap = request.params.get("max_tokens")
        if fault is None and cap is not None and len(chunks) > cap:
            # A provider stops at its output limit: usage first, then truncation.
            fault = Fault("truncation", after_chunks=cap)
        if fault is not None:
            chunks = chunks[: fault.after_chunks]
            self._clock.advance(fault.delay_ms)
        for i, chunk in enumerate(chunks):
            self._clock.advance(self._first_token_delay_ms if i == 0 else self._chunk_delay_ms)
            yield StreamPiece(text=chunk)
        if fault is not None and fault.kind != "truncation":
            raise AttemptFailure(fault.kind)
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        yield StreamPiece(
            usage=Usage(input_tokens=input_tokens, output_tokens=len(chunks)),
            model_version=request.model,
        )
        if fault is not None:
            raise AttemptFailure(fault.kind)
