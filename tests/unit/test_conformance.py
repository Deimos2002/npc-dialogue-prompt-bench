"""The fake client passes the provider conformance fixtures every adapter must pass (T10, T11)."""

import pytest

from npcbench.providers.base import AttemptFailure, StreamPiece
from npcbench.providers.conformance import CASES, ConformanceError, check_stream
from npcbench.providers.fake import FakeClient, FakeClock, Fault, fault_sequence
from npcbench.schemas import ChatRequest, Message

REQUEST = ChatRequest(model="fake-1", messages=[Message(role="user", content="Hello there")])


def _fake(case):
    clock = FakeClock()
    fault = {
        "ok": None,
        "timeout": Fault("timeout", delay_ms=30_000),
        "transport": Fault("transport", after_chunks=1),
        "truncation": Fault("truncation", after_chunks=2),
        "malformed": Fault("parse", after_chunks=1),
    }[case]
    return FakeClient(
        reply=lambda request: "Coin first, then talk.",
        clock=clock,
        faults=fault_sequence(fault),
    )


@pytest.mark.parametrize("case", CASES)
def test_the_fake_client_conforms(case):
    check_stream(_fake(case), REQUEST, case)


def test_fault_sequence_applies_faults_in_call_order_then_none():
    clock = FakeClock()
    client = FakeClient(
        reply=lambda request: "Fine.",
        clock=clock,
        faults=fault_sequence(Fault("timeout", delay_ms=100), None),
    )
    with pytest.raises(AttemptFailure) as caught:
        list(client.stream(REQUEST))
    assert caught.value.kind == "timeout"
    assert clock.now_ms() == 100
    assert "".join(p.text for p in client.stream(REQUEST)) == "Fine."
    assert "".join(p.text for p in client.stream(REQUEST)) == "Fine."


def test_only_truncation_reports_usage_before_failing():
    def pieces(fault):
        client = FakeClient(
            reply=lambda r: "a b c", clock=FakeClock(), faults=fault_sequence(fault)
        )
        seen = []
        with pytest.raises(AttemptFailure):
            for piece in client.stream(REQUEST):
                seen.append(piece)
        return seen

    assert any(p.usage for p in pieces(Fault("truncation", after_chunks=2)))
    for kind in ("timeout", "transport", "parse"):
        assert not any(p.usage for p in pieces(Fault(kind, after_chunks=2)))


class _NoUsageClient:
    def stream(self, request):
        yield StreamPiece(text="Hi")


class _LeakyClient:
    def stream(self, request):
        yield StreamPiece(text="Hi")
        raise ConnectionError("reset")


def test_conformance_rejects_a_stream_without_final_usage():
    with pytest.raises(ConformanceError, match="usage"):
        check_stream(_NoUsageClient(), REQUEST, "ok")


def test_conformance_rejects_failures_that_are_not_attempt_failures():
    with pytest.raises(ConformanceError, match="AttemptFailure"):
        check_stream(_LeakyClient(), REQUEST, "transport")


def test_the_fake_client_truncates_at_its_token_cap():
    client = FakeClient(reply=lambda r: "one two three four", clock=FakeClock())
    capped = REQUEST.model_copy(update={"params": {"max_tokens": 2}})
    pieces = []
    with pytest.raises(AttemptFailure) as caught:
        for piece in client.stream(capped):
            pieces.append(piece)
    assert caught.value.kind == "truncation"
    assert "".join(p.text for p in pieces) == "one two "
    assert pieces[-1].usage.output_tokens == 2
