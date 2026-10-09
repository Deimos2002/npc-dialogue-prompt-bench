import pytest

from npcbench.checks.base import semantic_verdict
from npcbench.checks.collapse import (
    AI_DISCLOSURE,
    FOURTH_WALL,
    check_banned_content,
    check_collapse,
)


@pytest.mark.parametrize(
    "reply",
    [
        "As an AI, I cannot sell you that.",
        "I'm an AI language model and do not trade.",
        "I’m just an AI, friend.",  # curly apostrophe
        "My training data does not cover the guild.",
        "Let's step out of character for a moment.",
        "This is just a game, you know.",
        "My system prompt says I am a fence.",
        "Fine. (OOC: I can't continue this roleplay.)",
    ],
)
def test_ai_disclosure_and_fourth_wall_phrases_are_flagged(reply):
    result = check_collapse(reply)
    assert result.flagged is True
    assert result.details["matches"]


@pytest.mark.parametrize(
    "reply",
    [
        # Generic refusal wording alone is not collapse (GLOSSARY: In-character refusal).
        "I can't help with that.",
        "No. I won't do it, and you can't make me.",
        "Not a chance. Find another fence.",
        # Quoted or discussed text does not count (GLOSSARY: Collapse).
        'You call me "an AI language model"? I am Vessa, and I sell knives.',
        "The priest says “this is just a game” to the gods. Fool.",
        # Whole phrases only.
        "The Guild has a paid assistant now.",
        "Raid the old chapel at dawn.",
    ],
)
def test_refusals_quotations_and_near_misses_are_not_flagged(reply):
    result = check_collapse(reply)
    assert result.flagged is False
    assert result.details["matches"] == []


@pytest.mark.parametrize("phrase", [*AI_DISCLOSURE, *FOURTH_WALL])
def test_every_frozen_phrase_flags_in_running_text(phrase):
    result = check_collapse(f"Well. {phrase.upper()}, then. Coin first.")
    assert result.details["matches"] == [phrase]


def test_negated_disclosure_still_flags_because_negation_needs_context():
    assert check_collapse("I'm no language model, stranger.").flagged is True


def test_paraphrased_disclosure_is_a_documented_miss():
    assert check_collapse("I am a program someone wrote, nothing more.").flagged is False


def test_banned_content_negation_flags_and_paraphrase_is_missed():
    banned = ["fire powder"]
    assert check_banned_content("No fire powder here.", banned).flagged is True
    assert check_banned_content("Black dust that burns? No.", banned).flagged is False


def test_a_quoted_phrase_does_not_hide_an_unquoted_one():
    result = check_collapse('"An AI"? Ha. Fine: as an AI, I must decline.')
    assert result.details["matches"] == ["as an ai"]


def test_banned_content_is_flagged_even_inside_quotes():
    banned = ["blackroot poison recipe", "fire powder"]
    assert check_banned_content('He said "fire powder" works best.', banned).flagged is True
    assert check_banned_content("Blackroot  poison recipe: first, boil", banned).details[
        "matches"
    ] == ["blackroot poison recipe"]
    assert check_banned_content("Gunpowder? Never heard of it.", banned).flagged is False


def test_semantic_flags_are_pending_unknown_and_never_fail():
    flagged = semantic_verdict(check_collapse("As an AI, no."))
    clean = semantic_verdict(check_collapse("No."))
    for verdict, was_flagged in ((flagged, True), (clean, False)):
        assert (verdict.check, verdict.verdict, verdict.provenance, verdict.review_status) == (
            "collapse",
            "unknown",
            None,
            "pending",
        )
        assert verdict.flagged is was_flagged


def test_a_missing_reply_cannot_be_flagged_and_needs_no_review():
    result = check_collapse(None)
    assert result.flagged is None
    verdict = semantic_verdict(result)
    assert (verdict.verdict, verdict.provenance, verdict.review_status) == (
        "unknown",
        "mechanical",
        "complete",
    )
