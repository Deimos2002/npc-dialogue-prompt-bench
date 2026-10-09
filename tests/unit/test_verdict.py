import pytest

from npcbench.schemas import Verdict


def _verdict(**fields):
    return Verdict.model_validate({"check": "lore", **fields})


@pytest.mark.parametrize(
    "fields",
    [
        {"verdict": "unknown", "provenance": None, "review_status": "pending", "flagged": True},
        {"verdict": "unknown", "provenance": "adjudicated", "review_status": "complete"},
        {"verdict": "pass", "provenance": "assumed", "review_status": "complete", "flagged": False},
        {"verdict": "fail", "provenance": "mechanical", "review_status": "complete"},
        {"verdict": "unknown", "provenance": "mechanical", "review_status": "complete"},
        {"verdict": "pass", "provenance": "judge", "review_status": "complete"},
    ],
)
def test_valid_verdicts(fields):
    _verdict(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        # A pending review has not happened, so it cannot have decided anything.
        {"verdict": "pass", "provenance": None, "review_status": "pending"},
        {"verdict": "unknown", "provenance": "adjudicated", "review_status": "pending"},
        {"verdict": "fail", "provenance": None, "review_status": "complete"},
        {"verdict": "fail", "provenance": "assumed", "review_status": "complete"},
        {"verdict": "pass", "provenance": "assumed", "review_status": "complete", "flagged": True},
        {"verdict": "pass", "provenance": "pending", "review_status": "complete"},
    ],
)
def test_inconsistent_verdicts_are_rejected(fields):
    with pytest.raises(ValueError):
        _verdict(**fields)


def test_adjudication_keeps_the_original_judge_output():
    verdict = _verdict(
        verdict="fail",
        provenance="adjudicated",
        review_status="complete",
        judge_output="greedy: yes",
    )
    assert verdict.judge_output == "greedy: yes"
