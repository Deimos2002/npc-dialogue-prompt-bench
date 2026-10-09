"""`overplay_rate` check: reply length budget and verbal-tic cap (protocol).

A proxy for caricature, not a complete measure of characterization quality (§9). A
mechanical check, so its counting rules are frozen here:

- Words: whitespace-separated tokens.
- Tics: matched by the frozen phrase rules in `npcbench.checks.matching` (case-insensitive,
  whole phrases, longest match first, overlapping tics count once). Quoted text counts like
  any other text.
"""

from __future__ import annotations

from npcbench.checks.base import CheckResult
from npcbench.checks.matching import find_phrases
from npcbench.schemas import OverplayLimits


def count_tics(text: str, tics: list[str]) -> int:
    return len(find_phrases(text, tics))


def check_overplay(reply: str | None, limits: OverplayLimits) -> CheckResult:
    """Flag a reply over its length budget or tic cap; a missing reply cannot be evaluated."""
    if reply is None:
        return CheckResult(check="overplay", flagged=None, details={"reasons": ["no_reply"]})
    words = len(reply.split())
    tics = count_tics(reply, limits.tics)
    reasons = []
    if words > limits.max_words:
        reasons.append("length")
    if tics > limits.max_tics:
        reasons.append("tics")
    return CheckResult(
        check="overplay",
        flagged=bool(reasons),
        details={"words": words, "tics": tics, "reasons": reasons},
    )
