"""Private run scoring policy: raw checks, audit selection and human precedence."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any

from npcbench.adjudication import Adjudication, apply_adjudications, pending_flags
from npcbench.cohort import ReviewCohort, apply_cohort, audit_sample, for_review, semantic_metrics
from npcbench.replies import Reply
from npcbench.report import compute_metrics, metric_rows, table_metrics
from npcbench.schemas import CharacterSheet, Scenario
from npcbench.scoring import Scored, verdicts_for

# Fixed so interval estimates remain reproducible across replay and adjudication.
BOOTSTRAP_SEED = 0


@dataclass(frozen=True)
class ScoredRun:
    """A run's replies and raw checks, with how its verdicts become final."""

    scenarios: list[Scenario]
    character: CharacterSheet
    replies: list[Reply]
    raw_checks: list[Scored]
    cohort: ReviewCohort | None

    @functools.cached_property
    def scenarios_by_id(self) -> dict[str, Scenario]:
        return {s.id: s for s in self.scenarios}

    @functools.cached_property
    def audit_reply_ids(self) -> set[str]:
        if self.cohort is None:
            return set()
        return audit_sample(self.raw_checks, self.scenarios_by_id, self.cohort)

    def eligible_adjudication_keys(self) -> set[tuple[str, str]] | None:
        """What an import may resolve: the review set and any mechanical verdict."""
        if self.cohort is None:
            return None
        review = self.pending_reviews(self.effective_checks({}))
        return {(s.recording.key, s.verdict.check) for s in review} | {
            (s.recording.key, s.verdict.check)
            for s in self.raw_checks
            if s.verdict.provenance == "mechanical"
        }

    def effective_checks(self, adjudications: dict[tuple[str, str], Adjudication]) -> list[Scored]:
        """Raw checks, then the review cohort's assumed passes, then human adjudication."""
        scored = self.raw_checks
        if self.cohort is not None:
            scored = apply_cohort(scored, self.cohort, self.audit_reply_ids)
        return apply_adjudications(scored, adjudications)

    def pending_reviews(self, effective: list[Scored]) -> list[Scored]:
        if self.cohort is None:
            return pending_flags(effective)
        return for_review(effective, self.cohort, self.audit_reply_ids)

    def metrics(
        self, run_id: str, adjudications: dict[tuple[str, str], Adjudication]
    ) -> dict[str, Any]:
        effective = self.effective_checks(adjudications)
        metrics = compute_metrics(
            run_id, self.scenarios, self.replies, verdicts_for(effective, "overplay")
        )
        if self.cohort is not None:
            metrics.update(
                semantic_metrics(effective, self.scenarios_by_id, self.cohort, self.audit_reply_ids)
            )
        cohort = None if self.cohort is None else self.cohort.replicates
        rows = metric_rows(effective, self.replies, self.scenarios_by_id, cohort)
        metrics.update(table_metrics(rows, self.scenarios, seed=BOOTSTRAP_SEED))
        return metrics
