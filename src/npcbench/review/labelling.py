"""Blind labelling: the label sampler, blinded items and the labels file (protocol).

Labels validate the judge and nothing else (GLOSSARY: Label). The labeller sees one reply
with its conversation, scenario class and story point, and the character sheet; never the
strategy, arm, prompt version, model, latency, cost or check results. Items are built from
an allowlist of fields, so nothing else can leak into them.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from npcbench.judge.questions import trait_questions
from npcbench.replies import Reply, conversation_before
from npcbench.schemas import CharacterSheet, Scenario
from npcbench.scoring import Scored

SCHEME = (
    "Stratified round robin over arm × model × class × outcome cells (outcome: flagged when"
    " any check flagged or failed the reply, otherwise unflagged), each cell shuffled by the seed."
    " Calibration examples are drawn first; validation replies come only from other families."
)


# Rater ids are short plain tokens, so they are safe in file names, URLs and logs.
RATER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_LABEL_LOCK = threading.Lock()


class LabelSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    seed: int
    scheme: str
    strata: dict[str, int]
    calibration: list[str]
    validation: list[str]
    calibration_families: list[str]
    validation_families: list[str]


class LabelRecord(BaseModel):
    """One rater's per-trait answers for one reply."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply_id: str = Field(min_length=1, max_length=128)
    rater: str = Field(pattern=RATER_PATTERN)
    answers: dict[str, Literal["yes", "no"]]


class LabelError(ValueError):
    pass


@dataclass(frozen=True)
class LabelCandidate:
    reply_id: str
    family_id: str
    arm_id: str
    model: str
    class_: str
    outcome: Literal["flagged", "unflagged"]

    @property
    def cell(self) -> str:
        return " | ".join((self.arm_id, self.model, self.class_, self.outcome))


def label_candidates(
    scored: Iterable[Scored], scenarios: dict[str, Scenario]
) -> list[LabelCandidate]:
    """Every reply with usable output, with the cell it is stratified into."""
    by_reply: dict[str, list[Scored]] = {}
    for s in scored:
        by_reply.setdefault(s.recording.key, []).append(s)
    candidates = []
    for key, checks in by_reply.items():
        rec = checks[0].recording
        if rec.reply_text is None:
            continue
        flagged = any(s.verdict.flagged or s.verdict.verdict == "fail" for s in checks)
        scenario = scenarios[rec.scenario_id]
        candidates.append(
            LabelCandidate(
                reply_id=key,
                family_id=scenario.family_id,
                arm_id=rec.arm_id,
                model=rec.request.model,
                class_=scenario.class_,
                outcome="flagged" if flagged else "unflagged",
            )
        )
    return candidates


def _round_robin(
    candidates: list[LabelCandidate], size: int, rng: random.Random
) -> list[LabelCandidate]:
    cells: dict[str, list[LabelCandidate]] = {}
    for c in sorted(candidates, key=lambda c: c.reply_id):
        cells.setdefault(c.cell, []).append(c)
    queues = [cells[cell] for cell in sorted(cells)]
    for queue in queues:
        rng.shuffle(queue)
    rng.shuffle(queues)
    chosen: list[LabelCandidate] = []
    while len(chosen) < size and any(queues):
        for queue in queues:
            if queue and len(chosen) < size:
                chosen.append(queue.pop())
    return chosen


def draw_label_sample(
    candidates: list[LabelCandidate],
    *,
    run_id: str,
    validation_size: int,
    calibration_size: int,
    seed: int,
) -> LabelSample:
    """Calibration examples, then validation replies from disjoint families (§10 rule 10)."""
    if validation_size < 1 or calibration_size < 0:
        raise LabelError("Validation size must be positive and calibration size non-negative")
    rng = random.Random(seed)
    calibration = _round_robin(candidates, calibration_size, rng)
    held_back = {c.family_id for c in calibration}
    eligible = [c for c in candidates if c.family_id not in held_back]
    if len(calibration) != calibration_size:
        raise LabelError(
            f"Insufficient calibration replies: need {calibration_size}, have {len(calibration)}"
        )
    if len(eligible) < validation_size:
        raise LabelError(
            f"Insufficient validation replies outside calibration families: "
            f"need {validation_size}, have {len(eligible)}"
        )
    validation = _round_robin(eligible, validation_size, rng)
    strata: dict[str, int] = {}
    for c in validation:
        strata[c.cell] = strata.get(c.cell, 0) + 1
    return LabelSample(
        run_id=run_id,
        seed=seed,
        scheme=SCHEME,
        strata=dict(sorted(strata.items())),
        calibration=[c.reply_id for c in calibration],
        validation=[c.reply_id for c in validation],
        calibration_families=sorted(held_back),
        validation_families=sorted({c.family_id for c in validation}),
    )


def label_item(reply: Reply, scenario: Scenario, character: CharacterSheet) -> dict[str, Any]:
    """The blinded view of one reply: an allowlist of fields, nothing about how it was made."""
    return {
        "reply_id": reply.key,
        "reply": reply.text,
        "conversation": conversation_before(reply.final),
        "player": scenario.turns[reply.turn_index].player,
        "scenario": {"class": scenario.class_, "story_point": scenario.story_point},
        "character": {
            "name": character.name,
            "summary": character.summary,
            "voice": character.voice.tone,
            "traits": [
                {"id": t.id, "description": t.description, "density": t.density}
                for t in character.traits
            ],
        },
        "questions": [{"trait_id": q.trait_id, "text": q.text} for q in trait_questions(character)],
    }


def serve_order(reply_ids: Iterable[str], *, seed: int, rater: str) -> list[str]:
    """A random order per rater, reproducible from the sample seed."""
    order = sorted(reply_ids)
    random.Random(f"{seed}|{rater}").shuffle(order)
    return order


def read_labels(path: Path) -> list[LabelRecord]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [LabelRecord.model_validate_json(line) for line in f if line.strip()]


def append_label(path: Path, record: LabelRecord, questions: dict[str, list[str]]) -> None:
    """Validate a label against its reply's questions and append it; one per rater and reply."""
    if record.reply_id not in questions:
        raise LabelError(f"unrecognised reply id {record.reply_id!r}")
    expected = set(questions[record.reply_id])
    if extra := set(record.answers) - expected:
        raise LabelError(f"unrecognised question ids {sorted(extra)}")
    if missing := expected - set(record.answers):
        raise LabelError(f"answer every question; missing {sorted(missing)}")
    # The local review server handles requests on several threads in one process.
    with _LABEL_LOCK:
        if any(
            r.reply_id == record.reply_id and r.rater == record.rater for r in read_labels(path)
        ):
            raise LabelError(f"rater {record.rater!r} already labelled reply {record.reply_id!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(record.model_dump_json() + "\n")
