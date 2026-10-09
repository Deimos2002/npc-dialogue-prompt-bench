"""Ollama adapter contract tests: a mock transport, never the network (protocol)."""

import json

import httpx
import pytest

from npcbench.providers.base import AttemptFailure
from npcbench.providers.conformance import CASES, check_stream
from npcbench.providers.ollama import OllamaClient, ProviderConfigError
from npcbench.schemas import ChatRequest, Message

REQUEST = ChatRequest(
    model="qwen3:4b",
    messages=[
        Message(role="system", content="You are Vessa."),
        Message(role="user", content="Selling?"),
    ],
    params={"temperature": 0.7, "max_tokens": 150, "seed": 3},
)
TAGS = {
    "models": [
        {
            "name": "qwen3:4b",
            "model": "qwen3:4b",
            "digest": "sha256:abc123",
            "details": {"quantization_level": "Q4_K_M"},
        }
    ]
}


@pytest.mark.parametrize("body", [[], {"models": None}, {"models": [None]},
                                 {"models": [{"name": "qwen3:4b", "details": "invalid"}]}])
def test_malformed_model_inventory_is_a_recordable_failure(body):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(AttemptFailure) as error:
        list(OllamaClient(http=http).stream(REQUEST))
    assert error.value.kind == "parse"


@pytest.mark.parametrize(
    "change", [{"done": "false"}, {"prompt_eval_count": True}, {"eval_count": -1}]
)
def test_invalid_terminal_types_are_not_accepted(change):
    chunk = {
        "done": True, "message": {"content": "reply"}, "prompt_eval_count": 1, "eval_count": 1,
    } | change
    client = _client(lambda r: httpx.Response(200, text=json.dumps(chunk) + "\n"))
    with pytest.raises(AttemptFailure) as error:
        list(client.stream(REQUEST))
    assert error.value.kind == "parse"


def _lines(*chunks, done_reason="stop"):
    lines = [{"message": {"role": "assistant", "content": c}, "done": False} for c in chunks]
    lines.append(
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": done_reason,
            "prompt_eval_count": 12,
            "eval_count": len(chunks),
        }
    )
    return "".join(json.dumps(line) + "\n" for line in lines)


def _client(chat, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if seen is not None:
            seen.append(json.loads(request.content))
        return chat(request)

    return OllamaClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


def _raise(error):
    def chat(request):
        raise error

    return chat


CASE_HANDLERS = {
    "ok": lambda request: httpx.Response(200, text=_lines("Coin ", "first.")),
    "timeout": _raise(httpx.ReadTimeout("slow")),
    "transport": _raise(httpx.ConnectError("refused")),
    "truncation": lambda request: httpx.Response(
        200, text=_lines("Coin ", "fir", done_reason="length")
    ),
    "malformed": lambda request: httpx.Response(
        200, text='{"message": {"content": "Hi"}}\nnot json\n'
    ),
}


@pytest.mark.parametrize("case", CASES)
def test_the_ollama_adapter_conforms(case):
    check_stream(_client(CASE_HANDLERS[case]), REQUEST, case)


def test_the_request_maps_messages_and_parameters():
    seen = []
    pieces = list(_client(CASE_HANDLERS["ok"], seen).stream(REQUEST))
    (body,) = seen
    assert body["model"] == "qwen3:4b"
    assert body["stream"] is True
    assert body["messages"] == [
        {"role": "system", "content": "You are Vessa."},
        {"role": "user", "content": "Selling?"},
    ]
    assert body["options"] == {"temperature": 0.7, "num_predict": 150, "seed": 3}
    assert "".join(p.text for p in pieces) == "Coin first."


def test_usage_and_the_model_digest_are_reported():
    pieces = list(_client(CASE_HANDLERS["ok"]).stream(REQUEST))
    final = pieces[-1]
    assert (final.usage.input_tokens, final.usage.output_tokens) == (12, 2)
    assert final.model_version == "qwen3:4b@sha256:abc123 (Q4_K_M)"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_server_overload_is_a_retryable_transport_failure(status):
    client = _client(lambda request: httpx.Response(status, text="busy"))
    with pytest.raises(AttemptFailure) as caught:
        list(client.stream(REQUEST))
    assert caught.value.kind == "transport"


def test_an_error_line_mid_stream_is_a_transport_failure():
    text = '{"message": {"content": "Hi"}, "done": false}\n{"error": "model crashed"}\n'
    with pytest.raises(AttemptFailure) as caught:
        list(_client(lambda request: httpx.Response(200, text=text)).stream(REQUEST))
    assert caught.value.kind == "transport"


def test_a_stream_that_stops_before_done_is_a_transport_failure():
    text = '{"message": {"content": "Hi"}, "done": false}\n'
    with pytest.raises(AttemptFailure) as caught:
        list(_client(lambda request: httpx.Response(200, text=text)).stream(REQUEST))
    assert caught.value.kind == "transport"


def test_an_unknown_model_stops_the_run_instead_of_recording_a_failure():
    client = _client(lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(ProviderConfigError, match="404"):
        list(client.stream(REQUEST))


def test_a_model_missing_from_the_local_store_is_a_configuration_error():
    request = REQUEST.model_copy(update={"model": "llama-nope"})
    with pytest.raises(ProviderConfigError, match="llama-nope"):
        list(_client(CASE_HANDLERS["ok"]).stream(request))


def test_unsupported_parameters_are_refused_rather_than_silently_dropped():
    request = REQUEST.model_copy(update={"params": {"temperature": 0.7, "logit_bias": {}}})
    with pytest.raises(ProviderConfigError, match="logit_bias"):
        list(_client(CASE_HANDLERS["ok"]).stream(request))


@pytest.mark.parametrize(
    "chunk",
    [
        {"message": None},
        {"message": {"content": 123}},
        {"done": True, "prompt_eval_count": "bad"},
        {"done": True, "eval_count": {}},
        [],
    ],
)
def test_malformed_chunk_fields_are_recorded_as_parse_failures(chunk):
    from npcbench.providers.fake import FakeClock
    from npcbench.runner import LiveSource

    source = LiveSource(
        _client(lambda r: httpx.Response(200, text=json.dumps(chunk) + "\n")), FakeClock()
    )
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
