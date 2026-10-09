"""Ollama adapter: a local model streamed over HTTP (protocol).

Streams `POST /api/chat` as newline-delimited JSON. Each line's text is a visible piece, so
the runner times the first visible token; the final `done` line carries token counts. The
model's digest and quantisation come from `/api/tags` and are recorded as its version.

Failures follow ADR 0002: timeouts are `timeout`; connection errors, overload (429, 5xx),
an error line mid-stream and a stream that stops before `done` are `transport`; a line that
is not the expected JSON is `parse`; `done_reason: length` is `truncation`. A request the
server rejects (other 4xx) or a model missing from the local store is a configuration error
that stops the run rather than a recorded failure.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from npcbench.providers.base import AttemptFailure, ProviderConfigError, StreamPiece
from npcbench.schemas import ChatRequest, Usage

DEFAULT_URL = "http://127.0.0.1:11434"
# Run parameters and the Ollama option each maps to; anything else is refused, never dropped.
_OPTIONS = {
    "temperature": "temperature",
    "max_tokens": "num_predict",
    "top_p": "top_p",
    "seed": "seed",
}


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_URL,
        timeout_s: float = 120.0,
        http: httpx.Client | None = None,
    ) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout_s)
        if http is not None and not str(self._http.base_url):
            self._http.base_url = base_url
        self._versions: dict[str, str] = {}

    def _model_version(self, model: str) -> str:
        """`name@digest (quantisation)`, looked up once per model."""
        if model not in self._versions:
            try:
                response = self._http.get("/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
            except httpx.TimeoutException:
                raise AttemptFailure("timeout") from None
            except (httpx.HTTPError, ValueError):
                raise AttemptFailure("transport") from None
            except AttributeError:
                raise AttemptFailure("parse") from None
            if not isinstance(models, list) or any(not isinstance(m, dict) for m in models):
                raise AttemptFailure("parse")
            found = next((m for m in models if model in (m.get("name"), m.get("model"))), None)
            if found is None:
                raise ProviderConfigError(f"Model {model!r} is not in the local Ollama store")
            details = found.get("details") or {}
            if not isinstance(details, dict):
                raise AttemptFailure("parse")
            quantisation = details.get("quantization_level", "unknown")
            self._versions[model] = f"{model}@{found.get('digest', 'unknown')} ({quantisation})"
        return self._versions[model]

    @staticmethod
    def _body(request: ChatRequest) -> dict[str, Any]:
        unknown = sorted(set(request.params) - set(_OPTIONS))
        if unknown:
            raise ProviderConfigError(f"Ollama does not support parameters {unknown}")
        return {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": True,
            "options": {_OPTIONS[name]: value for name, value in request.params.items()},
        }

    def stream(self, request: ChatRequest) -> Iterator[StreamPiece]:
        body = self._body(request)
        version = self._model_version(request.model)
        try:
            with self._http.stream("POST", "/api/chat", json=body) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    raise AttemptFailure("transport")
                if response.status_code >= 400:
                    raise ProviderConfigError(
                        f"Ollama rejected the request with HTTP {response.status_code}"
                    )
                yield from _safe_pieces(response.iter_lines(), version)
        except httpx.TimeoutException:
            raise AttemptFailure("timeout") from None
        except httpx.TransportError:
            raise AttemptFailure("transport") from None


def _pieces(lines: Iterator[str], version: str) -> Iterator[StreamPiece]:
    for line in lines:
        if not line.strip():
            continue
        try:
            chunk = json.loads(line)
            if "error" in chunk:
                raise AttemptFailure("transport")
            text = chunk.get("message", {}).get("content", "")
            done = chunk.get("done", False)
            if not isinstance(done, bool):
                raise ValueError("done is not boolean")
            if not isinstance(text, str):
                raise ValueError("content is not text")
        except (ValueError, AttributeError):
            raise AttemptFailure("parse") from None
        if text:
            yield StreamPiece(text=text)
        if done:
            if any(n is not None and (type(n) is not int or n < 0)
                   for n in (chunk.get("prompt_eval_count"), chunk.get("eval_count"))):
                raise AttemptFailure("parse")
            yield StreamPiece(
                usage=Usage(
                    input_tokens=chunk.get("prompt_eval_count"),
                    output_tokens=chunk.get("eval_count"),
                ),
                model_version=version,
            )
            if chunk.get("done_reason") == "length":
                raise AttemptFailure("truncation")
            return
    raise AttemptFailure("transport")


def _safe_pieces(lines: Iterator[str], version: str) -> Iterator[StreamPiece]:
    """Normalize malformed provider fields to the recorded parse-failure path."""
    try:
        yield from _pieces(lines, version)
    except (AttributeError, TypeError, ValueError):
        raise AttemptFailure("parse") from None
