import pytest

from npcbench.adjudication import Adjudication, apply_adjudications
from npcbench.cohort import (
    ReviewCohort,
    apply_cohort,
    audit_sample,
    for_review,
    semantic_metrics,
)
from npcbench.metrics.rates import wilson_interval
from npcbench.replies import group_replies
from npcbench.schemas import ChatRequest, Recording, Scenario, Timings, Usage, Verdict
from npcbench.scoring import Scored, ScoringContext, score
from tests.factories import character

COHORT = ReviewCohort(replicates=[0], audit_fraction=0.1, audit_seed=7)


def _scenario(sid, cls):
    return Scenario.model_validate(
        {
            "id": sid,
            "character": "vessa",
            "class": cls,
            "story_point": "act-1",
            "family_id": sid,
            "split": "dev",
            "turns": [{"player": "hi"}],
        }
    )


def _rec(sid, replicate, text, failure=None):
    return Recording(
        key=f"{sid}-r{replicate}",
        run_id="r1",
        scenario_id=sid,
        arm_id="direct@v1",
        strategy="direct",
        prompt_version="v1",
        turn_index=0,
        replicate=replicate,
        request=ChatRequest(model="fake-1", messages=[]),
        response_text=text,
        failure=failure,
        timings=Timings(ttft_ms=1.0, total_ms=2.0),
        usage=Usage(),
    )


@pytest.fixture
def run():
    """20 on_script and 3 spoiler scenarios, two replicates; one flagged cohort reply."""
    scenarios = [_scenario(f"on-{i:02d}", "on_script") for i in range(20)]
    scenarios += [_scenario(f"sp-{i}", "spoiler") for i in range(3)]
    recordings = []
    for replicate in (0, 1):
        for s in scenarios:
            text = "As an AI, no." if s.id == "on-00" else "Coin first."
            recordings.append(_rec(s.id, replicate, text))
    context = ScoringContext(character=character())
    scored = score(group_replies(recordings), context)
    return {s.id: s for s in scenarios}, scored


def _verdict(scored, key, check):
    return next(s.verdict for s in scored if s.recording.key == key and s.verdict.check == check)


def test_the_audit_samples_a_tenth_of_each_cell_of_unflagged_cohort_replies(run):
    scenarios, scored = run
    sample = audit_sample(scored, scenarios, COHORT)
    assert sample == audit_sample(scored, scenarios, COHORT)  # seeded
    on_script = {k for k in sample if k.startswith("on-")}
    spoiler = {k for k in sample if k.startswith("sp-")}
    # 19 unflagged on_script replies -> 2; 3 spoiler replies -> at least one.
    assert (len(on_script), len(spoiler)) == (2, 1)
    assert all(k.endswith("-r0") for k in sample)  # cohort only
    assert "on-00-r0" not in sample  # flagged replies are adjudicated, not audited


def test_another_seed_draws_another_sample(run):
    scenarios, scored = run
    draws = {
        frozenset(audit_sample(scored, scenarios, COHORT.model_copy(update={"audit_seed": s})))
        for s in range(5)
    }
    assert len(draws) > 1


def test_unflagged_unaudited_cohort_verdicts_become_assumed_passes(run):
    scenarios, scored = run
    sample = audit_sample(scored, scenarios, COHORT)
    unaudited = next(f"on-{i:02d}-r0" for i in range(1, 20) if f"on-{i:02d}-r0" not in sample)
    audited = next(iter(sample))
    effective = apply_cohort(scored, COHORT, sample)

    assumed = _verdict(effective, unaudited, "collapse")
    assert (assumed.verdict, assumed.provenance, assumed.review_status) == (
        "pass",
        "assumed",
        "complete",
    )
    for key, why in ((audited, "audited"), ("on-00-r0", "flagged"), ("on-05-r1", "outside")):
        verdict = _verdict(effective, key, "collapse")
        assert (verdict.verdict, verdict.review_status) == ("unknown", "pending"), why
    # A flagged reply is reviewed whole: its unflagged checks are not assumed to pass.
    assert _verdict(effective, "on-00-r0", "banned_content").review_status == "pending"
    # Mechanical verdicts are already complete and stay as they were.
    assert _verdict(effective, unaudited, "overplay").provenance == "mechanical"


def test_complete_verdicts_such_as_judge_output_are_not_touched(run):
    _, scored = run
    judged = Verdict(check="collapse", verdict="fail", provenance="judge", review_status="complete")
    scored = [Scored(scored[1].recording, scored[1].result, judged), *scored[2:]]
    assert apply_cohort(scored, COHORT, set())[0].verdict == judged


def test_review_covers_cohort_flags_and_the_audit_sample_only(run):
    scenarios, scored = run
    sample = audit_sample(scored, scenarios, COHORT)
    effective = apply_cohort(scored, COHORT, sample)
    keys = {s.recording.key for s in for_review(effective, COHORT, sample)}
    assert keys == {"on-00-r0", *sample}


def _adjudication(key, verdict, check="collapse"):
    return (key, check), Adjudication(reply_id=key, check=check, verdict=verdict)


def test_detected_semantic_error_rate_is_cohort_only_and_carries_the_audit(run):
    scenarios, scored = run
    sample = sorted(audit_sample(scored, scenarios, COHORT))
    adjudications = dict(
        [
            _adjudication("on-00-r0", "fail"),
            # The audit finds one miss among its three replies.
            _adjudication(sample[0], "fail"),
            _adjudication(sample[1], "pass"),
            _adjudication(sample[2], "pass"),
            *(_adjudication(key, "pass", "banned_content") for key in sample),
        ]
    )
    effective = apply_adjudications(apply_cohort(scored, COHORT, set(sample)), adjudications)
    metrics = semantic_metrics(effective, scenarios, COHORT, set(sample))

    collapse = metrics["detected_semantic_error_rate"]["collapse"]
    # Cohort replies only: 2 adjudicated fails; the rest are assumed or audited passes.
    assert collapse["all"] == {"k": 2, "n": 23, "unknown": 0}
    assert collapse["by_class"]["spoiler"]["n"] == 3
    # The flagged reply's banned_content verdict still awaits review.
    assert metrics["detected_semantic_error_rate"]["banned_content"]["all"]["unknown"] == 1

    audit = metrics["audit"]
    assert audit["cohort_replicates"] == [1]
    assert audit["coverage"] == {"k": 3, "n": 22}
    # Counted in replies, like coverage: a reply is a miss when any check failed it.
    assert (audit["miss_rate"]["k"], audit["miss_rate"]["n"]) == (1, 3)
    assert audit["miss_rate"]["interval"] == pytest.approx(list(wilson_interval(1, 3)))
    assert (audit["awaiting_review"], audit["inconclusive"]) == (0, 0)


def test_an_audited_reply_counts_once_and_only_when_fully_reviewed(run):
    scenarios, scored = run
    sample = sorted(audit_sample(scored, scenarios, COHORT))
    adjudications = dict(
        [
            # Two failed checks on one reply are one miss.
            _adjudication(sample[0], "fail"),
            _adjudication(sample[0], "fail", "banned_content"),
            # Inconclusive.
            _adjudication(sample[1], "unknown"),
            _adjudication(sample[1], "pass", "banned_content"),
            # Half reviewed: still awaiting.
            _adjudication(sample[2], "pass"),
        ]
    )
    effective = apply_adjudications(apply_cohort(scored, COHORT, set(sample)), adjudications)
    audit = semantic_metrics(effective, scenarios, COHORT, set(sample))["audit"]
    assert (audit["miss_rate"]["k"], audit["miss_rate"]["n"]) == (1, 1)
    assert (audit["inconclusive"], audit["awaiting_review"]) == (1, 1)


def test_wilson_interval():
    low, high = wilson_interval(1, 3)
    assert low == pytest.approx(0.0615, abs=1e-4)
    assert high == pytest.approx(0.7923, abs=1e-4)
    assert wilson_interval(0, 0) is None
