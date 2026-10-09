"""Stream the shared Chat Completions protocol for OpenAI, Groq, and Gemini.

Provider differences stay here: endpoint, credentials, token limit, reasoning and
usage fields. Retries remain the runner's responsibility. Supported model families
are deliberately bounded so native thinking is never silently enabled in a pilot.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from npcbench.providers.base import AttemptFailure, ProviderConfigError, StreamPiece
from npcbench.schemas import ChatRequest, Usage


@dataclass(frozen=True)
class _Endpoint:
    url: str
    key_variable: str
    token_parameter: str


_ENDPOINTS = {
    "openai": _Endpoint("https://api.openai.com/v1/", "OPENAI_API_KEY", "max_completion_tokens"),
    "groq": _Endpoint("https://api.groq.com/openai/v1/", "GROQ_API_KEY", "max_completion_tokens"),
    "gemini": _Endpoint(
        "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "max_tokens"
    ),
}
PROVIDERS = tuple(_ENDPOINTS)
DEFAULT_MAX_TOKENS = 512
_PASSED = frozenset({"temperature", "top_p", "max_tokens"})


class ChatCompletionsClient:
    def __init__(
        self,
        provider: str,
        *,
        api_key: str | None = None,
        reasoning: str = "disabled",
        http: httpx.Client | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        if provider not in _ENDPOINTS:
            raise ProviderConfigError(f"Unknown Chat Completions provider {provider!r}")
        self.provider = provider
        if reasoning not in {"disabled", "lowest"}:
            raise ProviderConfigError(f"Unknown reasoning setting {reasoning!r}")
        self._reasoning = reasoning
        self._endpoint = _ENDPOINTS[provider]
        key = api_key or os.environ.get(self._endpoint.key_variable)
        if not key:
            raise ProviderConfigError(f"Set {self._endpoint.key_variable} to run {provider}")
        self._key = key
        self._http = http or httpx.Client(base_url=self._endpoint.url, timeout=timeout_s)
        if http is not None and not str(self._http.base_url):
            self._http.base_url = self._endpoint.url

    def __repr__(self) -> str:
        return f"ChatCompletionsClient(provider={self.provider!r})"

    @property
    def reasoning(self) -> dict[str, Any]:
        if self._reasoning == "lowest":
            return {"setting": "lowest", "effort": "minimal", "disabled": False}
        return {"setting": "disabled", "disabled": True}

    def _reasoning_params(self, model: str) -> dict[str, Any]:
        if self._reasoning == "lowest":
            if self.provider == "gemini" and model == "gemini-3.5-flash-lite":
                return {"reasoning_effort": "minimal"}
            raise ProviderConfigError("Lowest reasoning is verified only for Gemini 3.5 Flash-Lite")
        if self.provider == "gemini" and model == "gemini-3.5-flash-lite":
            raise ProviderConfigError(
                "Gemini 3.5 Flash-Lite needs --reasoning lowest; thinking cannot be disabled"
            )
        if self.provider == "openai" and model.startswith(("gpt-4.1", "gpt-4o")):
            return {}
        if self.provider == "groq":
            if model in {"llama-3.3-70b-versatile", "llama-3.1-8b-instant"}:
                return {}
            if model == "qwen/qwen3.8-27b":
                return {"reasoning_effort": "none", "reasoning_format": "hidden"}
        if self.provider == "gemini" and model in {"gemini-2.5-flash", "gemini-2.5-flash-lite"}:
            return {"reasoning_effort": "none"}
        raise ProviderConfigError(
            f"{self.provider} model {model!r} has no verified thinking-off configuration "
            "in this adapter; choose a supported pilot model."
        )

    def _body(self, request: ChatRequest) -> dict[str, Any]:
        unknown = sorted(set(request.params) - _PASSED)
        if unknown:
            raise ProviderConfigError(f"{self.provider} does not pass parameters {unknown}")
        body = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
            self._endpoint.token_parameter: request.params.get("max_tokens", DEFAULT_MAX_TOKENS),
            **{k: v for k, v in request.params.items() if k != "max_tokens"},
            **self._reasoning_params(request.model),
        }
        if self.provider != "groq":
            body["stream_options"] = {"include_usage": True}
        return body

    def stream(self, request: ChatRequest) -> Iterator[StreamPiece]:
        body = self._body(request)
        try:
            with self._http.stream(
                "POST",
                "chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    raise AttemptFailure("transport")
                if response.status_code >= 400:
                    # Error bodies can echo credentials or prompt content. Do not expose them.
                    raise ProviderConfigError(
                        f"{self.provider} rejected the request with HTTP {response.status_code}; "
                        "check credentials, model access, parameters and account quota."
                    )
                description = (
                    "minimal; cannot be disabled" if self._reasoning == "lowest" else "disabled"
                )
                yield from _pieces(response.iter_lines(), description)
        except httpx.TimeoutException:
            raise AttemptFailure("timeout") from None
        except httpx.TransportError:
            raise AttemptFailure("transport") from None
        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
            raise AttemptFailure("parse") from None


def _usage(data: dict[str, Any]) -> Usage:
    values = [data.get("prompt_tokens"), data.get("completion_tokens")]
    if any(v is not None and (type(v) is not int or v < 0) for v in values):
        raise AttemptFailure("parse")
    return Usage(input_tokens=values[0], output_tokens=values[1])


def _pieces(lines: Iterator[str], reasoning: str = "disabled") -> Iterator[StreamPiece]:
    model = "unknown"
    usage = Usage()
    finish = None
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            if finish is None:
                raise AttemptFailure("transport")
            yield StreamPiece(usage=usage, model_version=f"{model} (reasoning: {reasoning})")
            if finish == "length":
                raise AttemptFailure("truncation")
            return
        event = json.loads(data)
        if not isinstance(event, dict):
            raise AttemptFailure("parse")
        if "error" in event:
            raise AttemptFailure("transport")
        if "model" in event:
            if not isinstance(event["model"], str):
                raise AttemptFailure("parse")
            model = event["model"]
        counts = event.get("usage")
        if counts is None and event.get("x_groq") is not None:
            counts = event["x_groq"].get("usage")
        if counts is not None:
            if not isinstance(counts, dict):
                raise AttemptFailure("parse")
            usage = _usage(counts)
        choices = event.get("choices")
        if not isinstance(choices, list):
            raise AttemptFailure("parse")
        for choice in choices:
            if choice["index"] != 0:
                raise AttemptFailure("parse")
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise AttemptFailure("parse")
            text = delta.get("content")
            if text is not None:
                if not isinstance(text, str) or finish is not None:
                    raise AttemptFailure("parse")
                yield StreamPiece(text=text)
            reason = choice.get("finish_reason")
            if reason is not None:
                if reason not in {"stop", "length", "content_filter"} or finish is not None:
                    raise AttemptFailure("parse")
                finish = reason
    raise AttemptFailure("transport")
