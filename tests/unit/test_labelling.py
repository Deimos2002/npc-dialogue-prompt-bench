"""Blind labelling (protocol), on fake multi-turn recordings."""

import json

import pytest

from npcbench.judge.questions import trait_questions
from npcbench.providers.fake import FakeClient, FakeClock
from npcbench.replies import group_replies
from npcbench.review.labelling import (
    LabelError,
    LabelRecord,
    append_label,
    draw_label_sample,
    label_candidates,
    label_item,
    read_labels,
    serve_order,
)
from npcbench.runner import LiveSource, run_arm
from npcbench.schemas import Arm, Scenario
from npcbench.scoring import ScoringContext, score
from tests.factories import character

CLASSES = ["on_script", "off_script", "adversarial", "spoiler"]
HIDDEN_KEYS = {"arm_id", "strategy", "prompt_version", "model", "timings", "latency", "verdict"}


def _scenarios():
    scenarios = []
    for cls in CLASSES:
        for i in range(3):
            turns = 2 if cls == "adversarial" else 1
            scenarios.append(
                Scenario.model_validate(
                    {
                        "id": f"{cls}-{i}",
                        "character": "vessa",
                        "class": cls,
                        "subtype": "authority_challenge" if cls == "adversarial" else None,
                        "story_point": "act-1",
                        "family_id": f"fam-{cls}-{i}",
                        "split": "dev",
                        "turns": [{"player": f"{cls} {i} line {t}"} for t in range(turns)],
                    }
                )
            )
    return scenarios


def _reply(request):
    line = request.messages[-1].content
    # Scenarios 0 and 2 of each class collapse, so the sample has flagged and clean replies.
    return "As an AI, I cannot." if line.split()[1] in {"0", "2"} else f"Coin first: {line}."


@pytest.fixture(scope="module")
def run():
    scenarios = _scenarios()
    sheet = character()
    recordings = []
    for model in ("fake-a", "fake-b"):
        for version in ("v1", "v2"):
            clock = FakeClock()
            recordings += run_arm(
                scenarios=scenarios,
                character=sheet,
                template="You are {{character_name}}.",
                run_id="r1",
                arm=Arm.of("direct", version),
                model=model,
                params={},
                source=LiveSource(FakeClient(reply=_reply, clock=clock), clock),
            )
    replies = group_replies(recordings)
    scored = score(replies, ScoringContext(character=sheet))
    by_id = {s.id: s for s in scenarios}
    return {"scenarios": by_id, "replies": replies, "scored": scored, "sheet": sheet}


def _keys(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_one_yes_no_question_per_dense_trait():
    questions = trait_questions(character())
    assert [q.trait_id for q in questions] == ["greedy"]  # "grudge" is sparse
    assert "Always angles for profit." in questions[0].text
    assert questions[0].text.endswith("Answer yes or no.")


def test_the_sample_stratifies_and_records_its_scheme_and_seed(run):
    candidates = label_candidates(run["scored"], run["scenarios"])
    sample = draw_label_sample(
        candidates, run_id="r1", validation_size=24, calibration_size=4, seed=3
    )
    assert sample == draw_label_sample(
        candidates, run_id="r1", validation_size=24, calibration_size=4, seed=3
    )
    assert (sample.seed, len(sample.validation), len(sample.calibration)) == (3, 24, 4)
    assert "arm × model × class × outcome" in sample.scheme
    by_id = {c.reply_id: c for c in candidates}
    chosen = [by_id[i] for i in sample.validation]
    assert {c.arm_id for c in chosen} == {"direct@v1", "direct@v2"}
    assert {c.model for c in chosen} == {"fake-a", "fake-b"}
    assert {c.class_ for c in chosen} == set(CLASSES)
    assert {c.outcome for c in chosen} == {"flagged", "unflagged"}
    assert sum(sample.strata.values()) == 24


def test_calibration_and_validation_come_from_disjoint_families(run):
    candidates = label_candidates(run["scored"], run["scenarios"])
    sample = draw_label_sample(
        candidates, run_id="r1", validation_size=40, calibration_size=4, seed=1
    )
    assert sample.calibration_families
    assert not set(sample.calibration_families) & set(sample.validation_families)
    by_id = {c.reply_id: c for c in candidates}
    assert {by_id[i].family_id for i in sample.validation} == set(sample.validation_families)


def test_the_labeller_never_sees_strategy_arm_model_or_scores(run):
    second_turn = next(r for r in run["replies"] if r.turn_index == 1)
    item = label_item(second_turn, run["scenarios"][second_turn.scenario_id], run["sheet"])
    assert not _keys(item) & HIDDEN_KEYS
    text = json.dumps(item)
    for identifying in ("direct@", "fake-a", "fake-b"):
        assert identifying not in text
    assert item["reply_id"] == second_turn.key
    assert item["reply"] == second_turn.text
    assert [t["speaker"] for t in item["conversation"]] == ["Player", "NPC"]
    assert item["player"].endswith("line 1")
    assert item["character"]["name"] == "Vessa"
    assert [q["trait_id"] for q in item["questions"]] == ["greedy"]


def test_items_are_served_in_a_seeded_random_order_per_rater():
    ids = [f"r{i}" for i in range(20)]
    order = serve_order(ids, seed=5, rater="ana")
    assert sorted(order) == sorted(ids)
    assert order != ids
    assert order == serve_order(ids, seed=5, rater="ana")
    assert order != serve_order(ids, seed=5, rater="ben")


def test_labels_are_appended_with_the_rater_id(tmp_path):
    path = tmp_path / "labels" / "blind_labels.jsonl"
    questions = {"x1": ["greedy"]}
    append_label(
        path, LabelRecord(reply_id="x1", rater="ana", answers={"greedy": "yes"}), questions
    )
    append_label(path, LabelRecord(reply_id="x1", rater="ben", answers={"greedy": "no"}), questions)
    assert [(r.rater, r.answers) for r in read_labels(path)] == [
        ("ana", {"greedy": "yes"}),
        ("ben", {"greedy": "no"}),
    ]


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        ({"reply_id": "nope", "rater": "ana", "answers": {"greedy": "yes"}}, "reply"),
        ({"reply_id": "x1", "rater": "ana", "answers": {}}, "every question"),
        ({"reply_id": "x1", "rater": "ana", "answers": {"greedy": "yes", "x": "no"}}, "question"),
    ],
)
def test_invalid_labels_are_rejected_and_not_written(tmp_path, record, problem):
    path = tmp_path / "labels.jsonl"
    with pytest.raises(LabelError, match=problem):
        append_label(path, LabelRecord.model_validate(record), {"x1": ["greedy"]})
    assert not path.exists()


@pytest.mark.parametrize("rater", ["", "a b", "x" * 65, "../etc"])
def test_rater_ids_are_short_plain_tokens(rater):
    with pytest.raises(ValueError):
        LabelRecord(reply_id="x1", rater=rater, answers={"greedy": "yes"})


def test_a_rater_labels_each_reply_once(tmp_path):
    path = tmp_path / "labels.jsonl"
    record = LabelRecord(reply_id="x1", rater="ana", answers={"greedy": "yes"})
    append_label(path, record, {"x1": ["greedy"]})
    with pytest.raises(LabelError, match="already"):
        append_label(path, record, {"x1": ["greedy"]})


@pytest.mark.parametrize(("validation", "calibration"), [(1, 3), (20, 1), (0, 0)])
def test_insufficient_or_invalid_sample_sizes_are_rejected(validation, calibration):
    from npcbench.review.labelling import LabelCandidate

    candidates = [
        LabelCandidate(f"r{i}", "one-family", "direct@v1", "m", "on_script", "unflagged")
        for i in range(2)
    ]
    with pytest.raises(LabelError):
        draw_label_sample(
            candidates,
            run_id="r1",
            validation_size=validation,
            calibration_size=calibration,
            seed=0,
        )
