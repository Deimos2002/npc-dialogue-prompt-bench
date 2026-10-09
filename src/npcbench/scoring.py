"""Score recorded replies: every check on every reply, as verdicts (protocol).

Run and replay both build the checks output here, so replay can require it to match.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from npcbench.checks.base import CheckResult, mechanical_verdict, semantic_verdict
from npcbench.checks.collapse import check_banned_content, check_collapse
from npcbench.checks.lore import check_entity_register, check_forbidden_facts, check_spoiler_facts
from npcbench.checks.overplay import check_overplay
from npcbench.replies import Reply
from npcbench.schemas import CharacterSheet, Recording, Scenario, Verdict, World


@dataclass(frozen=True)
class ScoringContext:
    """What the checks may consult beyond the reply itself."""

    character: CharacterSheet
    banned_content: list[str] = field(default_factory=list)
    world: World | None = None
    scenarios: dict[str, Scenario] = field(default_factory=dict)


@dataclass(frozen=True)
class Scored:
    recording: Recording
    result: CheckResult
    verdict: Verdict

    def row(self) -> dict[str, Any]:
        """One line of the checks output."""
        return {
            "key": self.recording.key,
            "scenario_id": self.recording.scenario_id,
            "turn_index": self.recording.turn_index,
            "details": self.result.details,
            **self.verdict.model_dump(mode="json", exclude={"judge_output"}),
        }


_Check = Callable[[str | None, Scenario | None, ScoringContext], CheckResult]


@dataclass(frozen=True)
class _CheckSpec:
    name: str
    run: _Check
    to_verdict: Callable[[CheckResult], Verdict]
    needs_world: bool = False


def _semantic(name: str, run: _Check, *, needs_world: bool = False) -> _CheckSpec:
    return _CheckSpec(name, run, semantic_verdict, needs_world)


# Every check, in output order. Lore checks run only when the run supplies a world.
CHECKS: tuple[_CheckSpec, ...] = (
    _CheckSpec(
        "overplay", lambda r, s, ctx: check_overplay(r, ctx.character.overplay), mechanical_verdict
    ),
    _semantic("collapse", lambda r, s, ctx: check_collapse(r)),
    _semantic("banned_content", lambda r, s, ctx: check_banned_content(r, ctx.banned_content)),
    _semantic(
        "entity_register",
        lambda r, s, ctx: check_entity_register(r, ctx.world, s, ctx.character),
        needs_world=True,
    ),
    _semantic(
        "forbidden_facts",
        lambda r, s, ctx: check_forbidden_facts(r, ctx.world, s),
        needs_world=True,
    ),
    _semantic(
        "spoiler_facts", lambda r, s, ctx: check_spoiler_facts(r, ctx.world, s), needs_world=True
    ),
)
SEMANTIC_CHECKS = frozenset(c.name for c in CHECKS if c.to_verdict is semantic_verdict)


def score(replies: list[Reply], context: ScoringContext) -> list[Scored]:
    """Every check on every reply, grouped by reply in run order.

    A reply is identified by its final attempt, which `Scored.recording` holds.
    """
    checks = [c for c in CHECKS if context.world is not None or not c.needs_world]
    scored = []
    for reply in replies:
        scenario = context.scenarios.get(reply.scenario_id)
        for check in checks:
            result = check.run(reply.text, scenario, context)
            scored.append(Scored(reply.final, result, check.to_verdict(result)))
    return scored


def verdicts_for(scored: list[Scored], check: str) -> list[Verdict]:
    """One check's verdicts, one per reply, in run order."""
    return [s.verdict for s in scored if s.verdict.check == check]
