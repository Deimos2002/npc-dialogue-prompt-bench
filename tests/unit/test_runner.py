from pathlib import Path

import pytest

from npcbench.loaders import load_character, load_scenarios
from npcbench.providers.base import AttemptFailure, StreamPiece
from npcbench.providers.fake import FakeClient, FakeClock, Fault, fault_sequence
from npcbench.recorder import MissingRecording, RecordingMismatch, RecordingStore
from npcbench.replies import group_replies
from npcbench.runner import PLAN_TOKEN_CAP, LiveSource, ReplaySource, arm_order, run_arm, run_arms
from npcbench.schemas import Arm, Scenario

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
ARM = Arm.of("direct", "v1")


@pytest.fixture
def inputs():
    return {
        "scenarios": load_scenarios(FIX / "scenarios.yaml"),
        "character": load_character(FIX / "character.yaml"),
        "template": (FIX / "prompt.md").read_text(encoding="utf-8"),
    }


def _live(inputs, clock):
    client = FakeClient(
        reply=lambda request: "Good knives. Cheap.",
        clock=clock,
        first_token_delay_ms=100,
        chunk_delay_ms=10,
    )
    return run_arm(
        **inputs,
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={"temperature": 0.7},
        source=LiveSource(client, clock),
    )


def test_live_run_records_request_response_timings_and_tokens(inputs):
    recs = _live(inputs, FakeClock())
    assert [r.scenario_id for r in recs] == ["c-fixture-on-001", "c-fixture-off-001"]
    first = recs[0]
    assert first.request.model == "fake-1"
    assert first.request.params == {"temperature": 0.7}
    assert first.request.messages[0].role == "system"
    assert "Fixture Fence" in first.request.messages[0].content
    assert first.request.messages[-1].content == "What are you selling today?"
    assert first.response_text == "Good knives. Cheap."
    assert first.timings.ttft_ms == 100
    assert first.timings.total_ms == 120
    assert first.usage.output_tokens == 3


def test_recordings_name_the_arm_call_kind_and_attempt(inputs):
    first = _live(inputs, FakeClock())[0]
    assert (first.arm_id, first.strategy, first.prompt_version) == ("direct@v1", "direct", "v1")
    assert (first.call_kind, first.attempt, first.replicate, first.turn_index) == (
        "reply",
        0,
        0,
        0,
    )


def test_two_versions_of_one_strategy_get_separate_recordings(inputs):
    clock = FakeClock()
    client = FakeClient(reply=lambda request: "Coin first.", clock=clock)
    keys = {
        rec.key
        for version in ("v1", "v2")
        for rec in run_arm(
            **inputs,
            run_id="r1",
            arm=Arm.of("direct", version),
            model="fake-1",
            params={},
            source=LiveSource(client, clock),
        )
    }
    assert len(keys) == 2 * len(inputs["scenarios"])


def test_a_plan_arm_needs_a_plan_prompt(inputs):
    with pytest.raises(ValueError, match="plan"):
        run_arm(
            **inputs,
            run_id="r1",
            arm=Arm.of("plan_generic", "v1"),
            model="fake-1",
            params={},
            source=ReplaySource(RecordingStore()),
        )


def test_replay_returns_identical_recordings(inputs):
    recs = _live(inputs, FakeClock())
    store = RecordingStore()
    for rec in recs:
        store.add(rec)
    replayed = run_arm(
        **inputs,
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={"temperature": 0.7},
        source=ReplaySource(store),
    )
    assert replayed == recs


def test_replay_rejects_a_recording_made_for_another_request(inputs):
    recs = _live(inputs, FakeClock())
    store = RecordingStore()
    swapped = recs[0].model_copy(update={"request": recs[1].request})
    store.add(swapped)
    store.add(recs[1])
    with pytest.raises(RecordingMismatch):
        run_arm(
            **inputs,
            run_id="r1",
            arm=ARM,
            model="fake-1",
            params={"temperature": 0.7},
            source=ReplaySource(store),
        )


def test_multi_turn_history_carries_only_visible_replies(inputs):
    two_turns = Scenario.model_validate(
        {
            "id": "c-fixture-multi-001",
            "character": "fixture-fence",
            "class": "adversarial",
            "subtype": "authority_challenge",
            "story_point": "act-1",
            "family_id": "fixture-multi-01",
            "split": "dev",
            "turns": [{"player": "Who are you?"}, {"player": "Really?"}],
        }
    )
    clock = FakeClock()
    replies = iter(["A trader.", "Truly."])
    client = FakeClient(reply=lambda request: next(replies), clock=clock)
    recs = run_arm(
        **{**inputs, "scenarios": [two_turns]},
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=LiveSource(client, clock),
    )
    second = recs[1].request.messages
    assert [m.role for m in second] == ["system", "user", "assistant", "user"]
    assert second[2].content == "A trader."
    store = RecordingStore()
    for rec in recs:
        store.add(rec)
    replayed = run_arm(
        **{**inputs, "scenarios": [two_turns]},
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=ReplaySource(store),
    )
    assert replayed == recs


class _LeadingWhitespaceClient:
    def __init__(self, clock):
        self._clock = clock

    def stream(self, request):
        self._clock.advance(5)
        yield StreamPiece(text="\n")
        self._clock.advance(45)
        yield StreamPiece(text="Hello")


def test_ttft_waits_for_visible_text(inputs):
    clock = FakeClock()
    recs = run_arm(
        **{**inputs, "scenarios": inputs["scenarios"][:1]},
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=LiveSource(_LeadingWhitespaceClient(clock), clock),
    )
    assert recs[0].timings.ttft_ms == 50
    assert recs[0].response_text == "\nHello"


def test_replay_without_recording_fails(inputs):
    with pytest.raises(MissingRecording):
        run_arm(
            **inputs,
            run_id="r1",
            arm=ARM,
            model="fake-1",
            params={"temperature": 0.7},
            source=ReplaySource(RecordingStore()),
        )


def _three_turn_script():
    return Scenario.model_validate(
        {
            "id": "c-fixture-press-001",
            "character": "fixture-fence",
            "class": "moral_pressure",
            "story_point": "act-1",
            "family_id": "fixture-press-01",
            "split": "dev",
            "turns": [{"player": "One?"}, {"player": "Two?"}, {"player": "Three?"}],
        }
    )


class _FailingOnTurnClient:
    """Answers until the request carries `fail_at` player lines, then fails the call."""

    def __init__(self, clock, fail_at, kind="timeout"):
        self._clock = clock
        self._fail_at = fail_at
        self._kind = kind

    def stream(self, request):
        players = sum(m.role == "user" for m in request.messages)
        self._clock.advance(30)
        if players == self._fail_at:
            yield StreamPiece(text="Half a")
            raise AttemptFailure(self._kind)
        yield StreamPiece(text=f"Answer {players}.")


def test_every_turn_of_a_script_is_run_in_order(inputs):
    clock = FakeClock()
    recs = run_arm(
        **{**inputs, "scenarios": [_three_turn_script()]},
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=LiveSource(_FailingOnTurnClient(clock, fail_at=None), clock),
    )
    assert [r.turn_index for r in recs] == [0, 1, 2]
    assert [r.response_text for r in recs] == ["Answer 1.", "Answer 2.", "Answer 3."]
    assert all(r.failure is None for r in recs)


def test_a_failed_call_ends_the_script_as_an_execution_failure(inputs):
    clock = FakeClock()
    script = {**inputs, "scenarios": [_three_turn_script(), *inputs["scenarios"]]}
    recs = run_arm(
        **script,
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=LiveSource(_FailingOnTurnClient(clock, fail_at=2, kind="truncation"), clock),
    )
    pressure = [r for r in recs if r.scenario_id == "c-fixture-press-001"]
    assert [r.turn_index for r in pressure] == [0, 1]
    failed = pressure[1]
    assert failed.failure == "truncation"
    assert failed.reply_text is None
    assert failed.response_text == "Half a"
    assert failed.timings.total_ms == 30
    # The failure ends only its own script.
    assert {r.scenario_id for r in recs} >= {"c-fixture-on-001", "c-fixture-off-001"}

    store = RecordingStore()
    for rec in recs:
        store.add(rec)
    replayed = run_arm(
        **script, run_id="r1", arm=ARM, model="fake-1", params={}, source=ReplaySource(store)
    )
    assert replayed == recs


def _single_turn(inputs):
    return {**inputs, "scenarios": inputs["scenarios"][:1]}


def _with_faults(inputs, *faults, backoff_ms=200):
    clock = FakeClock()
    client = FakeClient(
        reply=lambda request: "Coin first.",
        clock=clock,
        chunk_delay_ms=10,
        faults=fault_sequence(*faults),
    )
    source = LiveSource(client, clock, backoff_ms=backoff_ms)
    recs = run_arm(
        **_single_turn(inputs), run_id="r1", arm=ARM, model="fake-1", params={}, source=source
    )
    return recs


def test_a_timeout_is_retried_once_after_a_backoff(inputs):
    first, second = _with_faults(inputs, Fault("timeout", delay_ms=50))
    assert (first.attempt, first.failure, first.timings.total_ms) == (0, "timeout", 50)
    assert first.usage.output_tokens is None
    assert (second.attempt, second.failure, second.backoff_ms) == (1, None, 200)
    assert second.response_text == "Coin first."
    assert first.key != second.key


def test_a_second_transport_failure_is_an_execution_failure(inputs):
    recs = _with_faults(inputs, Fault("transport"), Fault("transport"))
    assert [(r.attempt, r.failure) for r in recs] == [(0, "transport"), (1, "transport")]


@pytest.mark.parametrize("kind", ["parse", "truncation"])
def test_parse_failures_and_truncation_are_never_retried(inputs, kind):
    recs = _with_faults(inputs, Fault(kind, after_chunks=1))
    assert [(r.attempt, r.failure) for r in recs] == [(0, kind)]


def test_replay_reproduces_every_attempt(inputs):
    recs = _with_faults(inputs, Fault("timeout", delay_ms=50))
    store = RecordingStore()
    for rec in recs:
        store.add(rec)
    replayed = run_arm(
        **_single_turn(inputs),
        run_id="r1",
        arm=ARM,
        model="fake-1",
        params={},
        source=ReplaySource(store),
    )
    assert replayed == recs


PLAN_TEMPLATE = (
    "You are {{character_name}}.\n{{character_sheet}}\n<!-- plan -->\nWrite a short plan.\n"
)


def _plan_reply(request):
    """Plans and replies the test can tell apart."""
    if request.messages[0].content.endswith("Write a short plan."):
        return f"PLAN for {request.messages[-1].content}"
    return f"Reply to {request.messages[-1].content}"


def _two_turns():
    return _three_turn_script().model_copy(update={"turns": _three_turn_script().turns[:2]})


def _plan_run(inputs, client, clock, arm=None):
    return run_arm(
        **{**inputs, "scenarios": [_two_turns()], "template": PLAN_TEMPLATE},
        run_id="r1",
        arm=arm or Arm.of("plan_in_character", "v1"),
        model="fake-1",
        params={"temperature": 0.7},
        source=LiveSource(client, clock),
    )


def test_a_plan_arm_makes_a_capped_plan_call_then_a_reply_call(inputs):
    clock = FakeClock()
    recs = _plan_run(inputs, FakeClient(reply=_plan_reply, clock=clock), clock)
    assert [(r.turn_index, r.call_kind) for r in recs] == [
        (0, "plan"),
        (0, "reply"),
        (1, "plan"),
        (1, "reply"),
    ]
    plan, reply = recs[0], recs[1]
    assert plan.request.params == {"temperature": 0.7, "max_tokens": PLAN_TOKEN_CAP}
    assert reply.request.params == {"temperature": 0.7}  # the same budget as direct
    assert "PLAN for One?" in reply.request.messages[0].content
    # Plans never enter the player-visible history of later turns.
    for later in recs[2:]:
        assert all("PLAN for One?" not in m.content for m in later.request.messages)
    assert [m.content for m in recs[3].request.messages[1:]] == [
        "One?",
        "Reply to One?",
        "Two?",
    ]


def test_ttft_counts_the_hidden_plan_as_delay(inputs):
    clock = FakeClock()
    client = FakeClient(reply=_plan_reply, clock=clock, first_token_delay_ms=40)
    (first, *_) = group_replies(_plan_run(inputs, client, clock))
    plan, reply = first.attempts
    assert plan.timings.total_ms == 40
    assert first.ttft_ms == 40 + reply.timings.ttft_ms == 80


def test_a_plan_cut_at_the_cap_is_used_not_a_failure(inputs):
    clock = FakeClock()

    def long_plan(request):
        is_plan = request.messages[0].content.endswith("Write a short plan.")
        return " ".join(["word"] * 200) if is_plan else "Ok."

    recs = _plan_run(inputs, FakeClient(reply=long_plan, clock=clock), clock)
    first = group_replies(recs)[0]
    assert first.attempts[0].failure == "truncation"
    assert first.failure is None
    assert first.text == "Ok."
    assert first.plan_truncated is True


def test_a_failed_plan_call_is_an_execution_failure(inputs):
    clock = FakeClock()
    client = FakeClient(
        reply=_plan_reply, clock=clock, faults=fault_sequence(Fault("parse", after_chunks=1))
    )
    recs = _plan_run(inputs, client, clock)
    assert [(r.call_kind, r.failure) for r in recs] == [("plan", "parse")]
    (reply,) = group_replies(recs)
    assert (reply.failure, reply.text) == ("parse", None)


def test_arm_order_is_a_counterbalanced_rotation():
    order = arm_order(["s0", "s1", "s2", "s3"], ["a", "b"])
    assert order == {"s0": ["a", "b"], "s1": ["b", "a"], "s2": ["a", "b"], "s3": ["b", "a"]}
    three = arm_order([f"s{i}" for i in range(6)], ["a", "b", "c"])
    firsts = [arms[0] for arms in three.values()]
    assert sorted(firsts) == ["a", "a", "b", "b", "c", "c"]


def test_several_arms_run_in_their_declared_order_and_replay(inputs):
    arms = [Arm.of("direct", "v1"), Arm.of("plan_generic", "v1")]
    templates = {
        arms[0].arm_id: inputs["template"],
        arms[1].arm_id: PLAN_TEMPLATE,
    }
    scenarios = inputs["scenarios"]
    order = arm_order([s.id for s in scenarios], [a.arm_id for a in arms])
    clock = FakeClock()
    common = {
        "scenarios": scenarios,
        "character": inputs["character"],
        "templates": templates,
        "arms": arms,
        "order": order,
        "run_id": "r1",
        "model": "fake-1",
        "params": {},
    }
    recs = run_arms(**common, source=LiveSource(FakeClient(reply=_plan_reply, clock=clock), clock))
    seen = []
    for rec in recs:
        if (rec.scenario_id, rec.arm_id) not in seen:
            seen.append((rec.scenario_id, rec.arm_id))
    assert seen == [(s, a) for s in order for a in order[s]]
    store = RecordingStore()
    for rec in recs:
        store.add(rec)
    assert run_arms(**common, source=ReplaySource(store)) == recs


def test_wrong_character_is_rejected_before_any_call(inputs):
    called = []
    inputs["scenarios"][-1] = inputs["scenarios"][-1].model_copy(update={"character": "other"})
    clock = FakeClock()
    client = FakeClient(reply=lambda request: called.append(request) or "Hi", clock=clock)
    with pytest.raises(ValueError, match="do not belong to character"):
        run_arm(
            **inputs,
            run_id="r1",
            arm=ARM,
            model="fake",
            params={},
            source=LiveSource(client, clock),
        )
    assert called == []
