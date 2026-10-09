from npcbench.replies import group_replies
from npcbench.schemas import ChatRequest, Recording, Timings, Usage


def _attempt(turn, attempt, *, failure=None, total=100.0, backoff=0.0, usage=None, text="Hi."):
    return Recording(
        key=f"t{turn}-a{attempt}",
        run_id="r1",
        scenario_id="s1",
        arm_id="direct@v1",
        strategy="direct",
        prompt_version="v1",
        turn_index=turn,
        attempt=attempt,
        request=ChatRequest(model="m", messages=[]),
        response_text=text,
        failure=failure,
        backoff_ms=backoff,
        timings=Timings(ttft_ms=None, total_ms=total),
        usage=usage or Usage(input_tokens=10, output_tokens=3),
    )


def test_a_reply_groups_every_attempt_of_its_turn():
    recordings = [
        _attempt(0, 0, failure="timeout", total=5000, usage=Usage()),
        _attempt(0, 1, backoff=1000, total=300),
        _attempt(1, 0, total=200),
    ]
    first, second = group_replies(recordings)
    assert [a.key for a in first.attempts] == ["t0-a0", "t0-a1"]
    assert first.key == "t0-a1"
    assert first.text == "Hi."
    assert first.failure is None
    assert first.retries == 1
    # Latency includes the failed attempt and the backoff (ADR 0002).
    assert first.latency_total_ms == 6300
    assert second.retries == 0


def test_a_reply_whose_final_attempt_failed_is_an_execution_failure():
    (reply,) = group_replies(
        [
            _attempt(0, 0, failure="transport", usage=Usage()),
            _attempt(0, 1, failure="transport", usage=Usage(), text="Hal"),
        ]
    )
    assert reply.failure == "transport"
    assert reply.text is None


def test_usage_an_attempt_never_reported_is_unknown_not_zero():
    (retried,) = group_replies([_attempt(0, 0, failure="timeout", usage=Usage()), _attempt(0, 1)])
    assert (retried.input_tokens, retried.output_tokens) == (10, 3)
    assert retried.usage_complete is False
    (clean,) = group_replies([_attempt(0, 0)])
    assert clean.usage_complete is True


def test_the_same_turn_under_two_models_is_two_replies():
    first = _attempt(0, 0)
    other_model = first.model_copy(
        update={"key": "other", "request": ChatRequest(model="m2", messages=[])}
    )
    assert len(group_replies([first, other_model])) == 2
