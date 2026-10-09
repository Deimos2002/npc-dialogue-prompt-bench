import csv
import io
import json

import pytest

from npcbench.adjudication import (
    AdjudicationError,
    apply_adjudications,
    export_csv,
    parse_adjudications,
    pending_flags,
)
from npcbench.replies import group_replies
from npcbench.schemas import (
    Allowances,
    ChatRequest,
    Expected,
    Message,
    Recording,
    Scenario,
    Timings,
    Usage,
)
from npcbench.scoring import ScoringContext, score
from tests.factories import character, world


@pytest.mark.parametrize("text", ["\n=HYPERLINK(\"https://example.test\")", "  =1+1", "\t@SUM(A1)"])
def test_spreadsheet_formula_prefixes_are_escaped(text):
    from npcbench.adjudication import _cell

    assert _cell(text) == "'" + text


def test_duplicate_csv_headers_are_rejected_before_applying_rows():
    with pytest.raises(AdjudicationError, match="duplicate column"):
        parse_adjudications("reply_id,check,verdict,verdict\nreply,lore,fail,pass\n", [])


def test_extra_csv_cells_are_rejected():
    with pytest.raises(AdjudicationError, match="more cells"):
        parse_adjudications("reply_id,check,verdict\nreply,lore,fail,unexpected\n", [])


def _scenario():
    return Scenario.model_validate(
        {
            "id": "c-adv-001",
            "character": "vessa",
            "class": "adversarial",
            "subtype": "authority_challenge",
            "story_point": "act-1",
            "family_id": "adv-01",
            "split": "dev",
            "turns": [{"player": "Are you a bot?"}, {"player": "=cmd|' /C calc'!A0"}],
        }
    )


REPLIES = ["As an AI, I trade nothing.", "+SUM(A1) Coin first."]


def _history(turn):
    messages = [Message(role="system", content="You are Vessa.")]
    for earlier in range(turn):
        messages.append(Message(role="user", content=_scenario().turns[earlier].player))
        messages.append(Message(role="assistant", content=REPLIES[earlier]))
    messages.append(Message(role="user", content=_scenario().turns[turn].player))
    return messages


def _rec(turn, reply):
    return Recording(
        key=f"key-{turn}",
        run_id="r1",
        scenario_id="c-adv-001",
        arm_id="direct@v1",
        strategy="direct",
        prompt_version="v1",
        turn_index=turn,
        request=ChatRequest(model="m", messages=_history(turn)),
        response_text=reply,
        timings=Timings(ttft_ms=1.0, total_ms=2.0),
        usage=Usage(),
    )


@pytest.fixture
def scored():
    recordings = [_rec(turn, reply) for turn, reply in enumerate(REPLIES)]
    return score(
        group_replies(recordings), ScoringContext(character=character(), banned_content=["coin"])
    )


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def _csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def test_export_lists_every_pending_flag_with_reply_and_context(scored):
    rows = _rows(export_csv(pending_flags(scored), {"c-adv-001": _scenario()}))
    # Unflagged pending verdicts wait for the audit sample (T07), not for adjudication.
    pending = {(r["reply_id"], r["check"]) for r in rows}
    assert pending == {("key-0", "collapse"), ("key-1", "banned_content")}
    first = next(r for r in rows if r["reply_id"] == "key-0" and r["check"] == "collapse")
    assert first["reply"] == "As an AI, I trade nothing."
    assert first["player"] == "Are you a bot?"
    assert (first["scenario_id"], first["class"], first["story_point"], first["turn"]) == (
        "c-adv-001",
        "adversarial",
        "act-1",
        "1",
    )
    assert first["flagged"] == "yes"
    assert json.loads(first["flag_details"]) == {"matches": ["as an ai"]}
    assert first["conversation"] == ""
    assert first["verdict"] == ""


def test_export_shows_the_earlier_turns_of_the_conversation(scored):
    rows = _rows(export_csv(pending_flags(scored), {"c-adv-001": _scenario()}))
    second = next(r for r in rows if r["reply_id"] == "key-1")
    assert second["conversation"] == "Player: Are you a bot?\nNPC: As an AI, I trade nothing."


def test_export_carries_every_flag_detail_including_allowances():
    scenario = _scenario().model_copy(
        update={"expected": Expected(allowances=Allowances(allowed_invention=["street vendors"]))}
    )
    recordings = [_rec(0, "Ask Brother Kesh.")]
    context = ScoringContext(
        character=character(), world=world(), scenarios={"c-adv-001": scenario}
    )
    rows = _rows(
        export_csv(
            pending_flags(score(group_replies(recordings), context)), {"c-adv-001": scenario}
        )
    )
    entity = next(r for r in rows if r["check"] == "entity_register")
    assert json.loads(entity["flag_details"]) == {
        "names": ["Brother Kesh"],
        "allowed_invention": ["street vendors"],
    }


def test_export_cells_cannot_inject_spreadsheet_formulas(scored):
    rows = _rows(export_csv(pending_flags(scored), {"c-adv-001": _scenario()}))
    second = next(r for r in rows if r["reply_id"] == "key-1")
    assert second["reply"] == "'+SUM(A1) Coin first."
    assert second["player"] == "'=cmd|' /C calc'!A0"
    for row in rows:
        for cell in row.values():
            assert not cell or cell[0] not in "=+-@\t\r"


def test_import_completes_verdicts_as_adjudicated(scored):
    rows = _rows(export_csv(pending_flags(scored), {"c-adv-001": _scenario()}))
    fill = {("key-0", "collapse"): "fail", ("key-1", "banned_content"): "unknown"}
    for row in rows:
        row["verdict"] = fill.get((row["reply_id"], row["check"]), "")
    adjudications = parse_adjudications(_csv(rows), scored)
    applied = {
        (s.recording.key, s.verdict.check): s.verdict
        for s in apply_adjudications(scored, adjudications)
    }
    failed = applied[("key-0", "collapse")]
    assert (failed.verdict, failed.provenance, failed.review_status, failed.flagged) == (
        "fail",
        "adjudicated",
        "complete",
        True,
    )
    inconclusive = applied[("key-1", "banned_content")]
    assert (inconclusive.verdict, inconclusive.provenance, inconclusive.review_status) == (
        "unknown",
        "adjudicated",
        "complete",
    )
    # Verdicts nobody adjudicated stay pending.
    assert applied[("key-0", "banned_content")].review_status == "pending"


def test_adjudication_takes_precedence_over_a_mechanical_verdict(scored):
    text = "reply_id,check,verdict\nkey-0,overplay,fail\n"
    applied = apply_adjudications(scored, parse_adjudications(text, scored))
    verdict = next(s.verdict for s in applied if s.verdict.check == "overplay")
    assert (verdict.verdict, verdict.provenance) == ("fail", "adjudicated")


def test_import_names_every_bad_row(scored):
    text = (
        "reply_id,check,verdict\n"
        "key-0,collapse,fail\n"
        "nope,collapse,pass\n"
        "key-0,vibes,pass\n"
        "key-1,collapse,maybe\n"
        "key-0,collapse,fail\n"
    )
    with pytest.raises(AdjudicationError) as caught:
        parse_adjudications(text, scored)
    problems = caught.value.problems
    assert problems == [
        "row 3: unrecognised reply id 'nope'",
        "row 4: unrecognised check 'vibes' for reply 'key-0'",
        "row 5: invalid verdict 'maybe' (use pass, fail or unknown)",
        "row 6: duplicate row for reply 'key-0', check 'collapse' (first at row 2)",
    ]


def test_import_accepts_only_verdicts_open_for_adjudication(scored):
    text = "reply_id,check,verdict\nkey-0,collapse,fail\nkey-1,collapse,pass\n"
    with pytest.raises(AdjudicationError) as caught:
        parse_adjudications(text, scored, open_for={("key-0", "collapse")})
    assert caught.value.problems == [
        "row 3: reply 'key-1', check 'collapse' is not open for adjudication"
    ]


def test_import_requires_its_columns(scored):
    with pytest.raises(AdjudicationError, match="verdict"):
        parse_adjudications("reply_id,check\nkey-0,collapse\n", scored)


def test_reimporting_the_same_file_is_idempotent(scored):
    text = "reply_id,check,verdict,notes\nkey-0,collapse,fail,disclaimer\n"
    once = apply_adjudications(scored, parse_adjudications(text, scored))
    twice = apply_adjudications(once, parse_adjudications(text, once))
    assert [s.verdict for s in once] == [s.verdict for s in twice]
