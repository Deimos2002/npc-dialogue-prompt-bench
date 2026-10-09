"""Replies: every recorded attempt of one turn, as the player experienced it (GLOSSARY: Reply).

A reply is made of one call (direct) or a plan call then a reply call, each of one or two
attempts. Checks and metrics count replies, never attempts (docs/adr/0002).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from npcbench.schemas import FailureKind, Recording


def plan_usable(plan: Recording) -> bool:
    """A plan cut at its token cap is still the bounded plan; any other failure is not."""
    return plan.failure in (None, "truncation")


def _final_attempts(attempts: tuple[Recording, ...]) -> list[Recording]:
    """The last attempt of each call, in call order."""
    finals: dict[str, Recording] = {}
    for a in attempts:
        finals[a.call_kind] = a
    return list(finals.values())


@dataclass(frozen=True)
class Reply:
    attempts: tuple[Recording, ...]

    @property
    def final(self) -> Recording:
        """The last attempt made; it decides whether the reply has usable output."""
        return self.attempts[-1]

    @property
    def key(self) -> str:
        """The reply's id: its final attempt's recording key."""
        return self.final.key

    @property
    def scenario_id(self) -> str:
        return self.final.scenario_id

    @property
    def turn_index(self) -> int:
        return self.final.turn_index

    @property
    def replicate(self) -> int:
        return self.final.replicate

    @property
    def failure(self) -> FailureKind | None:
        """Why the reply has no usable output, when a required call failed on its final attempt.

        A plan cut at its token cap is not a failure: it is the bounded plan.
        """
        for final in _final_attempts(self.attempts):
            if final.call_kind == "plan" and plan_usable(final):
                continue
            if final.failure is not None:
                return final.failure
        return None

    @property
    def text(self) -> str | None:
        """The player-visible output, or None for an execution failure."""
        if self.failure is not None or self.final.call_kind != "reply":
            return None
        return self.final.response_text

    @property
    def plan_truncated(self) -> bool:
        return any(
            f.call_kind == "plan" and f.failure == "truncation"
            for f in _final_attempts(self.attempts)
        )

    @property
    def ttft_ms(self) -> float | None:
        """Time to the first token the player sees, from before the first call.

        Plan calls, failed attempts and backoff before the final reply attempt all count
        as delay (protocol `latency_ttft_ms`).
        """
        if self.text is None or self.final.timings.ttft_ms is None:
            return None
        before = sum(a.timings.total_ms + a.backoff_ms for a in self.attempts[:-1])
        return before + self.final.backoff_ms + self.final.timings.ttft_ms

    @property
    def retries(self) -> int:
        return sum(a.attempt > 0 for a in self.attempts)

    @property
    def latency_total_ms(self) -> float:
        """Everything the player waited through: every attempt, failed ones and backoff."""
        return sum(a.timings.total_ms + a.backoff_ms for a in self.attempts)

    @property
    def input_tokens(self) -> int:
        """Known input tokens over every attempt; see `usage_complete`."""
        return sum(a.usage.input_tokens or 0 for a in self.attempts)

    @property
    def output_tokens(self) -> int:
        return sum(a.usage.output_tokens or 0 for a in self.attempts)

    @property
    def usage_complete(self) -> bool:
        """False when any attempt never reported usage, so the token sums are partial."""
        return all(
            a.usage.input_tokens is not None and a.usage.output_tokens is not None
            for a in self.attempts
        )


def conversation_before(recording: Recording) -> list[dict[str, str]]:
    """The turns before this one as the model saw them; the system prompt is left out."""
    speaker = {"user": "Player", "assistant": "NPC"}
    return [
        {"speaker": speaker[m.role], "text": m.content}
        for m in recording.request.messages[:-1]
        if m.role in speaker
    ]


def group_replies(recordings: Iterable[Recording]) -> list[Reply]:
    """Attempts grouped by turn, in the order the turns were first recorded."""
    groups: dict[tuple[str, str, str, int, int], list[Recording]] = {}
    for rec in recordings:
        turn = (rec.request.model, rec.arm_id, rec.scenario_id, rec.replicate, rec.turn_index)
        groups.setdefault(turn, []).append(rec)
    return [Reply(tuple(attempts)) for attempts in groups.values()]
