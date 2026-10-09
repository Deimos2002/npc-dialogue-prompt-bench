"""Hand adjudication round-trip: export pending verdicts to CSV, import the resolutions.

An imported adjudication completes a verdict with `adjudicated` provenance and takes
precedence over every other source (GLOSSARY: Adjudication, Provenance). Rows are keyed by
reply id (the reply's recording key) and check; a blank verdict cell leaves the verdict as
it was, so a half-filled sheet can be imported and re-imported.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from collections.abc import Iterable
from typing import get_args

from pydantic import BaseModel, ConfigDict

from npcbench.replies import conversation_before
from npcbench.schemas import Recording, Scenario, Verdict, VerdictValue
from npcbench.scoring import Scored

EXPORT_COLUMNS = (
    "reply_id",
    "check",
    "scenario_id",
    "class",
    "story_point",
    "turn",
    "conversation",
    "player",
    "reply",
    "flagged",
    "flag_details",
    "verdict",
    "notes",
)
REQUIRED_COLUMNS = ("reply_id", "check", "verdict")
VERDICT_VALUES = get_args(VerdictValue)
# A spreadsheet evaluates a cell starting with one of these as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class Adjudication(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reply_id: str
    check: str
    verdict: VerdictValue
    notes: str = ""


class AdjudicationError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if (
        text.startswith(_FORMULA_PREFIXES) or text.lstrip().startswith(_FORMULA_PREFIXES)
    ) else text


def _conversation(recording: Recording) -> str:
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in conversation_before(recording))


def pending_flags(scored: Iterable[Scored]) -> list[Scored]:
    """Pending flagged verdicts: what a run without a review cohort sends for adjudication."""
    return [s for s in scored if s.verdict.review_status == "pending" and s.verdict.flagged]


def export_csv(scored: Iterable[Scored], scenarios: dict[str, Scenario]) -> str:
    """The given pending verdicts, with each reply and the context needed to resolve it."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for s in scored:
        if s.verdict.review_status != "pending":
            continue
        rec = s.recording
        scenario = scenarios[rec.scenario_id]
        row = (
            rec.key,
            s.verdict.check,
            scenario.id,
            scenario.class_,
            scenario.story_point,
            rec.turn_index + 1,
            _conversation(rec),
            scenario.turns[rec.turn_index].player,
            rec.response_text,
            "yes" if s.verdict.flagged else "no",
            json.dumps(s.result.details, sort_keys=True, ensure_ascii=False),
            "",
            "",
        )
        writer.writerow([_cell(value) for value in row])
    return out.getvalue()


def parse_adjudications(
    text: str, scored: Iterable[Scored], open_for: set[tuple[str, str]] | None = None
) -> dict[tuple[str, str], Adjudication]:
    """Validated adjudications from a filled export; every bad row is named, none applied.

    `open_for`, when given, is every (reply id, check) a human may resolve; any other row is
    rejected, so a hand-edited sheet cannot reach verdicts the run never sent for review.
    """
    checks_by_reply: dict[str, set[str]] = {}
    for s in scored:
        checks_by_reply.setdefault(s.recording.key, set()).add(s.verdict.check)
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    if len(set(columns)) != len(columns):
        raise AdjudicationError(["duplicate column names"])
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise AdjudicationError([f"missing columns: {', '.join(missing)}"])

    problems: list[str] = []
    first_row: dict[tuple[str, str], int] = {}
    adjudications: dict[tuple[str, str], Adjudication] = {}
    for line, row in enumerate(reader, start=2):
        if None in row:
            problems.append(f"row {line}: more cells than column names")
            continue
        reply_id = (row["reply_id"] or "").strip()
        check = (row["check"] or "").strip()
        verdict = (row["verdict"] or "").strip().casefold()
        if reply_id not in checks_by_reply:
            problems.append(f"row {line}: unrecognised reply id {reply_id!r}")
            continue
        if check not in checks_by_reply[reply_id]:
            problems.append(f"row {line}: unrecognised check {check!r} for reply {reply_id!r}")
            continue
        if open_for is not None and (reply_id, check) not in open_for:
            problems.append(
                f"row {line}: reply {reply_id!r}, check {check!r} is not open for adjudication"
            )
            continue
        if (reply_id, check) in first_row:
            problems.append(
                f"row {line}: duplicate row for reply {reply_id!r}, check {check!r}"
                f" (first at row {first_row[reply_id, check]})"
            )
            continue
        first_row[reply_id, check] = line
        if not verdict:
            continue
        if verdict not in VERDICT_VALUES:
            problems.append(f"row {line}: invalid verdict {verdict!r} (use pass, fail or unknown)")
            continue
        adjudications[reply_id, check] = Adjudication(
            reply_id=reply_id, check=check, verdict=verdict, notes=(row.get("notes") or "").strip()
        )
    if problems:
        raise AdjudicationError(problems)
    return adjudications


def apply_adjudications(
    scored: Iterable[Scored], adjudications: dict[tuple[str, str], Adjudication]
) -> list[Scored]:
    """Replace each adjudicated verdict; the flag and any judge output are kept for audit."""
    applied = []
    for s in scored:
        adjudication = adjudications.get((s.recording.key, s.verdict.check))
        if adjudication is None:
            applied.append(s)
            continue
        verdict = Verdict(
            check=s.verdict.check,
            verdict=adjudication.verdict,
            provenance="adjudicated",
            review_status="complete",
            flagged=s.verdict.flagged,
            judge_output=s.verdict.judge_output,
        )
        applied.append(dataclasses.replace(s, verdict=verdict))
    return applied
