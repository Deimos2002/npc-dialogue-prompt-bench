"""Anthropic adapter: the hosted model, streamed over the Messages API (protocol).

Built on raw httpx streaming, so contract tests run on
`httpx.MockTransport` and the runner, not a client library, owns retries (ADR 0002).

- The API key is read from `ANTHROPIC_API_KEY` and lives only in the request header. It is
  never stored on a recording, in the run configuration or in an error message: provider
  error text is redacted before it is raised.
- Reasoning is pinned per run. `disabled` turns thinking off; `lowest` is for a model that
  cannot disable it: it runs at the lowest effort and is recorded as such (§7.3). Thinking
  arrives as hidden blocks, never as visible text, so it counts as delay.
- Failures: timeouts are `timeout`; connection errors, 429, 529, other 5xx, an `error`
  event and a stream that ends before `message_stop` are `transport`; a malformed event is
  `parse`; `stop_reason: max_tokens` is `truncation`. Authentication (401, 403) and other
  rejected requests are configuration errors that stop the run and are never retried.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any, Literal

import httpx

from npcbench.providers.base import AttemptFailure, ProviderConfigError, StreamPiece
from npcbench.schemas import ChatRequest, Usage

API_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
KEY_VARIABLE = "ANTHROPIC_API_KEY"
DEFAULT_MAX_TOKENS = 1024
# Run parameters passed straight to the API; anything else is refused, never dropped.
_PASSED = ("temperature", "top_p", "max_tokens")
Reasoning = Literal["disabled", "lowest"]
_REASONING = {
    "disabled": ({"thinking": {"type": "disabled"}}, "disabled"),
    "lowest": ({"output_config": {"effort": "low"}}, "lowest effort; cannot be disabled"),
}


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        reasoning: Reasoning = "disabled",
        base_url: str = API_URL,
        timeout_s: float = 120.0,
        http: httpx.Client | None = None,
    ) -> None:
        key = api_key or os.environ.get(KEY_VARIABLE)
        if not key:
            raise ProviderConfigError(f"Set {KEY_VARIABLE} to run the Anthropic provider")
        if reasoning not in _REASONING:
            raise ProviderConfigError(f"Unknown reasoning setting {reasoning!r}")
        self._key = key
        self._reasoning: Reasoning = reasoning
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout_s)
        if http is not None and not str(self._http.base_url):
            self._http.base_url = base_url

    def __repr__(self) -> str:
        return f"AnthropicClient(reasoning={self._reasoning!r})"

    @property
    def reasoning(self) -> dict[str, Any]:
        """The pinned reasoning setting, for the run configuration."""
        if self._reasoning == "disabled":
            return {"setting": "disabled", "thinking": "disabled", "disabled": True}
        return {"setting": "lowest", "thinking": "effort low", "disabled": False}

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "[redacted]")

    def _body(self, request: ChatRequest) -> dict[str, Any]:
        unknown = sorted(set(request.params) - set(_PASSED))
        if unknown:
            raise ProviderConfigError(f"The Anthropic adapter does not pass parameters {unknown}")
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        body: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.params.get("max_tokens", DEFAULT_MAX_TOKENS),
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
                if m.role != "system"
            ],
            "stream": True,
            **{k: v for k, v in request.params.items() if k != "max_tokens"},
            **_REASONING[self._reasoning][0],
        }
        if system:
            body["system"] = system
        return body

    def _rejected(self, response: httpx.Response) -> ProviderConfigError:
        try:
            response.read()
            error = response.json().get("error", {})
            detail = f"{error.get('type', 'error')}: {error.get('message', '')}"
        except (ValueError, AttributeError):
            detail = "unreadable error body"
        return ProviderConfigError(
            self._redact(
                f"Anthropic rejected the request with HTTP {response.status_code} ({detail})"
            )
        )

    def stream(self, request: ChatRequest) -> Iterator[StreamPiece]:
        body = self._body(request)
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION}
        try:
            with self._http.stream("POST", "/v1/messages", json=body, headers=headers) as response:
                status = response.status_code
                if status in (429, 529) or status >= 500:
                    raise AttemptFailure("transport")
                if status >= 400:
                    raise self._rejected(response)
                yield from _safe_pieces(response.iter_lines(), _REASONING[self._reasoning][1])
        except httpx.TimeoutException:
            raise AttemptFailure("timeout") from None
        except httpx.TransportError:
            raise AttemptFailure("transport") from None


def _events(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Server-sent events: each `data:` line holds one JSON event."""
    for line in lines:
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[len("data:") :])
        except ValueError:
            raise AttemptFailure("parse") from None
        if not isinstance(event, dict):
            raise AttemptFailure("parse")
        yield event


def _pieces(lines: Iterator[str], reasoning: str) -> Iterator[StreamPiece]:
    model = "unknown"
    input_tokens = output_tokens = None
    stop_reason = None
    started = False
    for event in _events(lines):
        kind = event.get("type")
        if kind == "error":
            raise AttemptFailure("transport")
        if kind == "message_start":
            if started:
                raise AttemptFailure("parse")
            started = True
            message = event.get("message", {})
            model = message.get("model", model)
            input_tokens = message.get("usage", {}).get("input_tokens")
        elif kind == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text")
                if not isinstance(text, str):
                    raise AttemptFailure("parse")
                yield StreamPiece(text=text)
        elif kind == "message_delta":
            stop_reason = event.get("delta", {}).get("stop_reason", stop_reason)
            output_tokens = event.get("usage", {}).get("output_tokens", output_tokens)
        elif kind == "message_stop":
            if not started or not isinstance(stop_reason, str) or not stop_reason:
                raise AttemptFailure("parse")
            if any(n is not None and (type(n) is not int or n < 0)
                   for n in (input_tokens, output_tokens)):
                raise AttemptFailure("parse")
            yield StreamPiece(
                usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
                model_version=f"{model} (reasoning: {reasoning})",
            )
            if stop_reason == "max_tokens":
                raise AttemptFailure("truncation")
            return
    raise AttemptFailure("transport")


def _safe_pieces(lines: Iterator[str], version: str) -> Iterator[StreamPiece]:
    """Normalize malformed provider fields to the recorded parse-failure path."""
    try:
        yield from _pieces(lines, version)
    except (AttributeError, TypeError, ValueError):
        raise AttemptFailure("parse") from None
