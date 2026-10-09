"""Pacing preserves the recordings' measured time and replay identity."""

from npcbench.pacing import PacedSource
from npcbench.providers.fake import FakeClient, FakeClock, echo_reply
from npcbench.runner import LiveSource
from npcbench.schemas import ChatRequest, Message


def test_pause_between_attempts_is_outside_recorded_latency():
    clock = FakeClock()
    source = PacedSource(LiveSource(FakeClient(reply=echo_reply, clock=clock), clock), clock, 30000)
    request = ChatRequest(model="fake-1", messages=[Message(role="user", content="Hi")])
    meta = {
        "run_id": "r",
        "scenario_id": "s",
        "arm_id": "direct@v1",
        "strategy": "direct",
        "prompt_version": "v1",
        "turn_index": 0,
        "call_kind": "reply",
        "attempt": 0,
    }
    first = source.fetch(key="a", request=request, meta=meta)
    first_end = clock.now_ms()
    second = source.fetch(key="b", request=request, meta=meta)
    assert clock.now_ms() - first_end == 30000 + second.timings.total_ms
    assert first.timings == second.timings
    assert first.response_text == second.response_text
    assert second.key == "b"
