"""Hosted protocol contracts on MockTransport; no keys or network required."""

import json

import httpx
import pytest

from npcbench.providers.base import AttemptFailure, ProviderConfigError
from npcbench.providers.chat_completions import ChatCompletionsClient
from npcbench.providers.conformance import CASES, check_stream
from npcbench.schemas import ChatRequest, Message

KEY = "test-provider-SECRET"
MODELS = {
    "openai": "gpt-4.1-mini-2025-04-14",
    "groq": "qwen/qwen3.8-27b",
    "gemini": "gemini-2.5-flash-lite",
}


def _request(provider):
    return ChatRequest(
        model=MODELS[provider],
        messages=[
            Message(role="system", content="Stay in character."),
            Message(role="user", content="Advice?"),
        ],
        params={"temperature": 0.7, "max_tokens": 150},
    )


def _event(text=None, finish=None, **extra):
    return {
        "model": "returned-model-version",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}],
        **extra,
    }


def _sse(*events, done=True):
    stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    return stream + ("data: [DONE]\n\n" if done else "")


def _client(provider, handler, seen=None):
    def capture(request):
        if seen is not None:
            seen.append(request)
        return handler(request)

    return ChatCompletionsClient(
        provider, api_key=KEY, http=httpx.Client(transport=httpx.MockTransport(capture))
    )


def _fault(kind):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout")
        if kind == "transport":
            raise httpx.ConnectError("transport")
        if kind == "malformed":
            return httpx.Response(200, text="data: {broken\n\n")
        return httpx.Response(
            200,
            text=_sse(
                _event("Coin "),
                _event("first."),
                _event(finish="length" if kind == "truncation" else "stop"),
            ),
        )

    return handler


@pytest.mark.parametrize("provider", MODELS)
@pytest.mark.parametrize("case", CASES)
def test_each_provider_conforms(provider, case):
    check_stream(_client(provider, _fault(case)), _request(provider), case)


@pytest.mark.parametrize("provider", MODELS)
def test_auth_messages_caps_usage_and_model_version(provider):
    seen = []
    counts = {"prompt_tokens": 31, "completion_tokens": 4}
    final = _event(
        finish="stop",
        **({"x_groq": {"usage": counts}} if provider == "groq" else {"usage": counts}),
    )
    client = _client(
        provider, lambda r: httpx.Response(200, text=_sse(_event("Advice."), final)), seen
    )
    pieces = list(client.stream(_request(provider)))
    request = seen[0]
    body = json.loads(request.content)
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert (
        request.url.path
        == {
            "openai": "/v1/chat/completions",
            "groq": "/openai/v1/chat/completions",
            "gemini": "/v1beta/openai/chat/completions",
        }[provider]
    )
    assert body["messages"] == [m.model_dump() for m in _request(provider).messages]
    assert body["temperature"] == 0.7
    assert body["max_tokens" if provider == "gemini" else "max_completion_tokens"] == 150
    assert body["stream"] is True
    assert (pieces[-1].usage.input_tokens, pieces[-1].usage.output_tokens) == (31, 4)
    assert pieces[-1].model_version == "returned-model-version (reasoning: disabled)"
    if provider == "openai":
        assert "reasoning_effort" not in body
    else:
        assert body["reasoning_effort"] == "none"
    if provider == "groq":
        assert body["reasoning_format"] == "hidden"
        assert "stream_options" not in body
    assert KEY not in repr(client)


def test_usage_only_final_chunk_and_hidden_reasoning_do_not_become_dialogue():
    stream = _sse(
        {"model": "m", "choices": [{"index": 0, "delta": {"reasoning": "hidden"}}]},
        _event("Visible."),
        _event(finish="stop"),
        {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
    )
    pieces = list(
        _client("openai", lambda r: httpx.Response(200, text=stream)).stream(_request("openai"))
    )
    assert "".join(p.text for p in pieces) == "Visible."
    assert pieces[-1].usage.input_tokens == 3


@pytest.mark.parametrize(
    "event",
    [
        [],
        {"choices": None},
        {"choices": [None]},
        _event(["wrong"]),
        _event(finish="tool_calls"),
        _event(finish="stop", usage={"prompt_tokens": -1}),
        _event(finish="stop", usage={"completion_tokens": True}),
        _event(finish="stop", x_groq=[]),
        _event(finish="stop", model=123),
    ],
)
def test_malformed_fields_are_parse_failures(event):
    with pytest.raises(AttemptFailure) as error:
        list(
            _client("openai", lambda r: httpx.Response(200, text=_sse(event))).stream(
                _request("openai")
            )
        )
    assert error.value.kind == "parse"


@pytest.mark.parametrize(
    "stream",
    [
        _sse(_event("Partial"), done=False),
        _sse(_event("Partial")),
        _sse(_event("Partial"), _event(finish="stop"), done=False),
        _sse({"error": {"message": KEY}}),
    ],
)
def test_incomplete_streams_and_error_events_are_transport_failures(stream):
    with pytest.raises(AttemptFailure) as error:
        list(
            _client("openai", lambda r: httpx.Response(200, text=stream)).stream(_request("openai"))
        )
    assert error.value.kind == "transport"
    assert KEY not in str(error.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_errors_are_retryable(status):
    with pytest.raises(AttemptFailure) as error:
        list(_client("groq", lambda r: httpx.Response(status)).stream(_request("groq")))
    assert error.value.kind == "transport"


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_rejections_do_not_expose_error_body_or_key(status):
    with pytest.raises(ProviderConfigError) as error:
        list(
            _client("openai", lambda r: httpx.Response(status, text=KEY)).stream(_request("openai"))
        )
    assert str(status) in str(error.value)
    assert KEY not in str(error.value)


@pytest.mark.parametrize("provider", MODELS)
def test_no_key_is_a_configuration_error(provider, monkeypatch):
    monkeypatch.delenv(f"{provider.upper()}_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match=f"{provider.upper()}_API_KEY"):
        ChatCompletionsClient(provider)


def test_unsupported_model_or_parameter_fails_before_any_http_call():
    def unexpected(request):
        pytest.fail("No HTTP request should be made")

    client = _client("openai", unexpected)
    request = _request("openai")
    with pytest.raises(ProviderConfigError, match="thinking-off"):
        list(client.stream(request.model_copy(update={"model": "gpt-oss-20b"})))
    with pytest.raises(ProviderConfigError, match="parameters"):
        list(client.stream(request.model_copy(update={"params": {"seed": 1}})))


def test_gemini_35_records_minimal_native_reasoning_and_refuses_false_thinking_off():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=_sse(_event("Advice."), _event(finish="stop")))

    request = _request("gemini").model_copy(update={"model": "gemini-3.5-flash-lite"})
    client = ChatCompletionsClient(
        "gemini",
        api_key=KEY,
        reasoning="lowest",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    pieces = list(client.stream(request))
    assert seen[0]["reasoning_effort"] == "minimal"
    assert client.reasoning == {"setting": "lowest", "effort": "minimal", "disabled": False}
    assert "minimal; cannot be disabled" in pieces[-1].model_version
    with pytest.raises(ProviderConfigError, match="thinking cannot be disabled"):
        list(_client("gemini", handler).stream(request))
