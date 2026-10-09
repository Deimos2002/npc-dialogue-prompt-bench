"""The semantic review cohort and its audit (protocol; docs/adr/0001).

A run declares its cohort before it executes (v0.1: replicate 1, stored as index 0). Inside
the cohort every flagged reply is adjudicated whole (each of its semantic checks) and a
seeded sample of unflagged replies is audited; the remaining unflagged replies' semantic
verdicts become assumed passes, and each semantic check reports a detected error rate
alongside the audit's coverage and miss rate, both counted in replies. Outside
the cohort semantic verdicts stay unknown and pending, and no such rate is reported.

Verdicts that are already complete (mechanical, judge or adjudicated) are never changed
here, so indicative judge metrics keep their own coverage.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from npcbench.metrics.rates import Rate, verdict_rate, verdict_rates_by, wilson_interval
from npcbench.schemas import Scenario, Verdict
from npcbench.scoring import SEMANTIC_CHECKS, Scored


class ReviewCohort(BaseModel):
    """Declared in the run configuration before execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    replicates: list[int] = Field(default_factory=lambda: [0])
    audit_fraction: float = Field(default=0.1, gt=0, le=1)
    audit_seed: int


def _in_cohort(s: Scored, cohort: ReviewCohort) -> bool:
    return s.recording.replicate in cohort.replicates


def _by_reply(scored: Iterable[Scored]) -> dict[str, list[Scored]]:
    replies: dict[str, list[Scored]] = {}
    for s in scored:
        replies.setdefault(s.recording.key, []).append(s)
    return replies


def _flagged_replies(scored: Iterable[Scored]) -> set[str]:
    """Replies any semantic check flagged; a human reads each of them whole."""
    return {
        s.recording.key for s in scored if s.verdict.check in SEMANTIC_CHECKS and s.verdict.flagged
    }


def _audit_candidates(scored: Iterable[Scored], cohort: ReviewCohort) -> dict[str, Scored]:
    """Cohort replies with usable output and no semantic flag, keyed by reply id."""
    candidates = {}
    for key, checks in _by_reply(scored).items():
        semantic = [s for s in checks if s.verdict.check in SEMANTIC_CHECKS]
        if (
            semantic
            and _in_cohort(semantic[0], cohort)
            and all(s.verdict.flagged is False for s in semantic)
        ):
            candidates[key] = semantic[0]
    return candidates


def audit_sample(
    scored: Iterable[Scored], scenarios: dict[str, Scenario], cohort: ReviewCohort
) -> set[str]:
    """A seeded share of unflagged cohort replies, at least one per class × arm × model."""
    cells: dict[tuple[str, str, str], list[str]] = {}
    for key, s in _audit_candidates(scored, cohort).items():
        rec = s.recording
        cell = (scenarios[rec.scenario_id].class_, rec.arm_id, rec.request.model)
        cells.setdefault(cell, []).append(key)
    sample: set[str] = set()
    for cell, keys in sorted(cells.items()):
        rng = random.Random(f"{cohort.audit_seed}|{'|'.join(cell)}")
        size = math.ceil(cohort.audit_fraction * len(keys))
        sample.update(rng.sample(sorted(keys), size))
    return sample


def apply_cohort(scored: Iterable[Scored], cohort: ReviewCohort, audited: set[str]) -> list[Scored]:
    """Pending verdicts of unflagged, unaudited cohort replies become assumed passes."""
    scored = list(scored)
    reviewed = audited | _flagged_replies(scored)
    applied = []
    for s in scored:
        v = s.verdict
        if (
            v.review_status == "pending"
            and v.flagged is False
            and _in_cohort(s, cohort)
            and s.recording.key not in reviewed
        ):
            assumed = Verdict(
                check=v.check,
                verdict="pass",
                provenance="assumed",
                review_status="complete",
                flagged=False,
            )
            s = replace(s, verdict=assumed)
        applied.append(s)
    return applied


def for_review(scored: Iterable[Scored], cohort: ReviewCohort, audited: set[str]) -> list[Scored]:
    """Pending verdicts a human resolves: every check of flagged or audited cohort replies."""
    scored = list(scored)
    reviewed = audited | _flagged_replies(scored)
    return [
        s
        for s in scored
        if s.verdict.review_status == "pending"
        and _in_cohort(s, cohort)
        and s.recording.key in reviewed
    ]


def _audit_outcome(checks: list[Scored]) -> str:
    """One audited reply: awaiting until every semantic check is reviewed, then a miss if
    any check failed it, inconclusive if any review was, otherwise a pass."""
    verdicts = [s.verdict for s in checks if s.verdict.check in SEMANTIC_CHECKS]
    if any(v.review_status == "pending" for v in verdicts):
        return "awaiting"
    if any(v.verdict == "fail" for v in verdicts):
        return "miss"
    if any(v.verdict == "unknown" for v in verdicts):
        return "inconclusive"
    return "pass"


def semantic_metrics(
    effective: list[Scored],
    scenarios: dict[str, Scenario],
    cohort: ReviewCohort,
    audited: set[str],
) -> dict[str, Any]:
    """Detected semantic error rates for the cohort, with the audit reported alongside."""
    cohort_rows = [
        (scenarios[s.recording.scenario_id].class_, s.verdict)
        for s in effective
        if s.verdict.check in SEMANTIC_CHECKS and _in_cohort(s, cohort)
    ]
    rates: dict[str, Any] = {}
    for check in sorted({v.check for _, v in cohort_rows}):
        rows = [(cls, v.verdict) for cls, v in cohort_rows if v.check == check]
        by_class = verdict_rates_by(rows, key=lambda row: row[0], verdict=lambda row: row[1])
        rates[check] = {
            "all": verdict_rate(verdict for _, verdict in rows).as_dict(),
            "by_class": {cls: rate.as_dict() for cls, rate in by_class.items()},
        }

    outcomes = [
        _audit_outcome(checks) for key, checks in _by_reply(effective).items() if key in audited
    ]
    misses = outcomes.count("miss")
    decided = misses + outcomes.count("pass")
    interval = wilson_interval(misses, decided)
    candidates = _audit_candidates(effective, cohort)
    coverage_cells: dict[str, list[int]] = {}
    for key, s in candidates.items():
        cell = coverage_cells.setdefault(
            f"{s.recording.arm_id}|{s.recording.request.model}", [0, 0]
        )
        cell[0] += key in audited
        cell[1] += 1
    return {
        "detected_semantic_error_rate": rates,
        "audit": {
            "cohort_replicates": [r + 1 for r in cohort.replicates],
            "audit_fraction": cohort.audit_fraction,
            "audit_seed": cohort.audit_seed,
            "coverage": Rate(len(audited), len(candidates)).as_dict(),
            "coverage_by_arm_model": {
                cell: Rate(k, n).as_dict() for cell, (k, n) in sorted(coverage_cells.items())
            },
            "miss_rate": {
                "k": misses,
                "n": decided,
                "interval": None if interval is None else list(interval),
            },
            "inconclusive": outcomes.count("inconclusive"),
            "awaiting_review": outcomes.count("awaiting"),
        },
    }
