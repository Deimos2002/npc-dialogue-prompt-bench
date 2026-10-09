"""`turns_to_failure` for pressure scripts (protocol; GLOSSARY: Turns to failure)."""

from __future__ import annotations

from typing import Literal

from npcbench.schemas import VerdictValue

Outcome = Literal["failed", "censored", "incomplete"]


def script_outcome(verdicts: list[VerdictValue], turns: int) -> tuple[Outcome, int | None]:
    """Classify one script from its per-turn verdicts in turn order.

    `failed` at the first failing turn (one-based) when every earlier turn passed;
    `censored` at the turn count when every turn was observed passing; otherwise
    `incomplete`: an unknown verdict or a missing turn leaves the first failure unobserved.
    """
    for index, verdict in enumerate(verdicts):
        if verdict == "fail":
            return ("failed", index + 1)
        if verdict == "unknown":
            return ("incomplete", None)
    if len(verdicts) == turns:
        return ("censored", turns)
    return ("incomplete", None)
