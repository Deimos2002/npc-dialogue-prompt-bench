"""Anthropic adapter contract tests: a mock transport, never the network (protocol)."""

import json

import httpx
import pytest

from npcbench.providers.anthropic import AnthropicClient
from npcbench.providers.base import AttemptFailure, ProviderConfigError
from npcbench.providers.conformance import CASES, check_stream
from npcbench.schemas import ChatRequest, Message

KEY = "sk-ant-test-0000-SECRET"
REQUEST = ChatRequest(
    model="claude-test-1",
    messages=[
        Message(role="system", content="You are Vessa."),
        Message(role="user", content="Selling?"),
        Message(role="assistant", content="Knives."),
        Message(role="user", content="How much?"),
    ],
    params={"temperature": 0.7, "max_tokens": 150},
)


@pytest.mark.parametrize("events", [
    [{"type": "message_stop"}],
    [{"type": "message_start", "message": {}}, {"type": "message_stop"}],
    [{"type": "message_start", "message": {"usage": {"input_tokens": True}}},
     {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, {"type": "message_stop"}],
])
def test_incomplete_or_malformed_terminal_state_is_not_success(events):
    client = _client(lambda r: httpx.Response(200, text=_sse(*events)))
    with pytest.raises(AttemptFailure) as error:
        list(client.stream(REQUEST))
    assert error.value.kind == "parse"


def _sse(*events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _delta(index, delta):
    return {"type": "content_block_delta", "index": index, "delta": delta}


def _stream(*texts, stop_reason="end_turn", thinking=False):
    events = [
        {
            "type": "message_start",
            "message": {"model": "claude-test-1-20260901", "usage": {"input_tokens": 21}},
        }
    ]
    if thinking:
        events += [
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}},
            _delta(0, {"type": "thinking_delta", "thinking": "hmm"}),
            {"type": "content_block_stop", "index": 0},
        ]
    events.append(
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}
    )
    events += [_delta(1, {"type": "text_delta", "text": t}) for t in texts]
    events += [
        {"type": "ping"},
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason},
            "usage": {"output_tokens": len(texts)},
        },
        {"type": "message_stop"},
    ]
    return _sse(*events)


def _client(chat, seen=None, reasoning="disabled", key=KEY):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return chat(request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicClient(api_key=key, reasoning=reasoning, http=http)


def _raise(error):
    def chat(request):
        raise error

    return chat


CASE_HANDLERS = {
    "ok": lambda r: httpx.Response(200, text=_stream("Coin ", "first.")),
    "timeout": _raise(httpx.ReadTimeout("slow")),
    "transport": _raise(httpx.ConnectError("refused")),
    "truncation": lambda r: httpx.Response(
        200, text=_stream("Coin ", "fi", stop_reason="max_tokens")
    ),
    "malformed": lambda r: httpx.Response(
        200,
        text=_sse({"type": "message_start", "message": {"model": "m", "usage": {}}})
        + "event: content_block_delta\ndata: {not json\n\n",
    ),
}


@pytest.mark.parametrize("case", CASES)
def test_the_anthropic_adapter_conforms(case):
    check_stream(_client(CASE_HANDLERS[case]), REQUEST, case)


def test_the_request_carries_the_key_version_system_and_messages():
    seen = []
    pieces = list(_client(CASE_HANDLERS["ok"], seen).stream(REQUEST))
    (request,) = seen
    assert request.url.path == "/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["model"] == "claude-test-1"
    assert body["stream"] is True
    assert body["system"] == "You are Vessa."
    assert body["messages"] == [
        {"role": "user", "content": "Selling?"},
        {"role": "assistant", "content": "Knives."},
        {"role": "user", "content": "How much?"},
    ]
    assert (body["max_tokens"], body["temperature"]) == (150, 0.7)
    assert body["thinking"] == {"type": "disabled"}
    assert "".join(p.text for p in pieces) == "Coin first."


def test_usage_and_the_pinned_reasoning_setting_are_reported():
    final = list(_client(CASE_HANDLERS["ok"]).stream(REQUEST))[-1]
    assert (final.usage.input_tokens, final.usage.output_tokens) == (21, 2)
    assert final.model_version == "claude-test-1-20260901 (reasoning: disabled)"


def test_a_model_that_cannot_disable_reasoning_runs_at_its_lowest_setting():
    seen = []
    thinking = lambda r: httpx.Response(200, text=_stream("Hi.", thinking=True))  # noqa: E731
    client = _client(thinking, seen, "lowest")
    pieces = list(client.stream(REQUEST))
    body = json.loads(seen[0].content)
    assert "thinking" not in body
    assert body["output_config"] == {"effort": "low"}
    # Hidden reasoning is never visible text.
    assert "".join(p.text for p in pieces) == "Hi."
    assert pieces[-1].model_version == (
        "claude-test-1-20260901 (reasoning: lowest effort; cannot be disabled)"
    )
    assert client.reasoning == {"setting": "lowest", "thinking": "effort low", "disabled": False}


@pytest.mark.parametrize("status", [429, 500, 529])
def test_rate_limits_overload_and_server_errors_are_retryable(status):
    client = _client(lambda r: httpx.Response(status, json={"error": {"type": "x"}}))
    with pytest.raises(AttemptFailure) as caught:
        list(client.stream(REQUEST))
    assert caught.value.kind == "transport"


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_errors_stop_the_run_and_are_never_retried(status):
    echo = {"error": {"type": "authentication_error", "message": f"bad key {KEY}"}}
    client = _client(lambda r: httpx.Response(status, json=echo))
    with pytest.raises(ProviderConfigError) as caught:
        list(client.stream(REQUEST))
    assert str(status) in str(caught.value)
    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value)


def test_a_bad_request_is_a_configuration_error_with_the_key_redacted():
    echo = {"error": {"type": "invalid_request_error", "message": f"no: {KEY}"}}
    client = _client(lambda r: httpx.Response(400, json=echo))
    with pytest.raises(ProviderConfigError) as caught:
        list(client.stream(REQUEST))
    assert "invalid_request_error" in str(caught.value)
    assert KEY not in str(caught.value)


def test_an_error_event_mid_stream_is_a_transport_failure():
    text = _sse(
        {"type": "message_start", "message": {"model": "m", "usage": {}}},
        {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}},
    )
    with pytest.raises(AttemptFailure) as caught:
        list(_client(lambda r: httpx.Response(200, text=text)).stream(REQUEST))
    assert caught.value.kind == "transport"


def test_a_stream_that_stops_before_message_stop_is_a_transport_failure():
    text = _sse({"type": "message_start", "message": {"model": "m", "usage": {}}})
    with pytest.raises(AttemptFailure) as caught:
        list(_client(lambda r: httpx.Response(200, text=text)).stream(REQUEST))
    assert caught.value.kind == "transport"


def test_the_key_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=_stream("Hi."))

    http = httpx.Client(transport=httpx.MockTransport(handler))
    list(AnthropicClient(http=http).stream(REQUEST))
    assert seen[0].headers["x-api-key"] == KEY


def test_a_missing_key_fails_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicClient()


def test_the_client_never_shows_its_key():
    client = _client(CASE_HANDLERS["ok"])
    assert KEY not in repr(client)
    assert KEY not in str(client.reasoning)


@pytest.mark.parametrize(
    "event",
    [
        {"type": "message_start", "message": None},
        {"type": "message_start", "message": {"usage": None}},
        {"type": "content_block_delta", "delta": None},
        {"type": "message_delta", "usage": None},
        {"type": "message_start", "message": {"usage": {"input_tokens": "bad"}}},
    ],
)
def test_malformed_event_fields_are_recorded_as_parse_failures(event):
    from npcbench.providers.fake import FakeClock
    from npcbench.runner import LiveSource

    text = _sse(event, {"type": "message_stop"})
    source = LiveSource(_client(lambda r: httpx.Response(200, text=text)), FakeClock())
    rec = source.fetch(
        key="bad",
        request=REQUEST,
        meta={
            "run_id": "r",
            "scenario_id": "s",
            "arm_id": "direct@v1",
            "strategy": "direct",
            "prompt_version": "v1",
            "turn_index": 0,
            "attempt": 0,
        },
    )
    assert rec.failure == "parse"
