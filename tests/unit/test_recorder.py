import pytest

from npcbench.recorder import MissingRecording, RecordingStore, request_key
from npcbench.schemas import ChatRequest, Message, Recording, Timings, Usage


def _req(content="u", **params):
    return ChatRequest(
        model="m",
        messages=[Message(role="system", content="s"), Message(role="user", content=content)],
        params=params,
    )


def _rec(request):
    return Recording(
        key=request_key(request),
        run_id="r1",
        scenario_id="s1",
        arm_id="direct@v1",
        strategy="direct",
        prompt_version="v1",
        turn_index=0,
        request=request,
        response_text="hello",
        timings=Timings(ttft_ms=10.0, total_ms=20.0),
        usage=Usage(input_tokens=5, output_tokens=1),
    )


def test_key_is_stable_across_param_order():
    assert request_key(_req(temperature=0.7, max_tokens=50)) == request_key(
        _req(max_tokens=50, temperature=0.7)
    )


def test_key_changes_with_messages_and_params():
    base = request_key(_req())
    assert request_key(_req(content="other")) != base
    assert request_key(_req(temperature=0.1)) != base


def test_same_request_in_another_slot_gets_its_own_key():
    request = _req()
    assert request_key(request, slot={"replicate": 0}) != request_key(
        request, slot={"replicate": 1}
    )


def test_store_roundtrip(tmp_path):
    rec = _rec(_req())
    store = RecordingStore()
    store.add(rec)
    path = tmp_path / "recordings.jsonl"
    store.save(path)
    assert RecordingStore.load(path).get(rec.key) == rec


def test_missing_recording_raises():
    with pytest.raises(MissingRecording):
        RecordingStore().get("absent")


def test_duplicate_key_is_rejected():
    rec = _rec(_req())
    store = RecordingStore()
    store.add(rec)
    with pytest.raises(ValueError):
        store.add(rec)
