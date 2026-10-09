"""Deterministic checks (protocol).

A check produces a flag. A mechanical check's flag is its verdict; a semantic check's flag
only starts a review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from npcbench.schemas import Verdict


@dataclass(frozen=True)
class CheckResult:
    """A check's raw outcome; `flagged` is None when the reply could not be evaluated."""

    check: str
    flagged: bool | None
    details: dict[str, Any] = field(default_factory=dict)


def mechanical_verdict(result: CheckResult) -> Verdict:
    """A mechanical check's flag is its verdict; an unevaluated reply is unknown, never a pass."""
    outcome = {True: "fail", False: "pass", None: "unknown"}[result.flagged]
    return Verdict(
        check=result.check,
        verdict=outcome,
        provenance="mechanical",
        review_status="complete",
        flagged=result.flagged,
    )


def semantic_verdict(result: CheckResult) -> Verdict:
    """A semantic check's result awaits review, flagged or not, so it is pending and unknown.

    A missing reply leaves nothing to review: the verdict is unknown and complete.
    """
    if result.flagged is None:
        return mechanical_verdict(result)
    return Verdict(
        check=result.check,
        verdict="unknown",
        provenance=None,
        review_status="pending",
        flagged=result.flagged,
    )
