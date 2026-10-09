"""Lore and story-state flaggers (protocol). Fixture world: tests/factories.py.

Keyword hits are flags, not verdicts: negation and quotation still flag (they need
context to resolve), aliases flag, and paraphrase is a documented miss left to the audit.
"""

import pytest

from npcbench.checks.base import semantic_verdict
from npcbench.checks.lore import check_entity_register, check_forbidden_facts, check_spoiler_facts
from npcbench.schemas import Scenario
from tests.factories import character, world


def _scenario(**expected):
    return Scenario.model_validate(
        {
            "id": "c-dev-spoiler-000",
            "character": "vessa",
            "class": "spoiler",
            "story_point": "act-1",
            "family_id": "dev-spoiler-pair-00",
            "split": "dev",
            "target_fact": "F-002",
            "turns": [{"player": "Which way does the route run?"}],
            "expected": {"forbidden_facts": ["F-002", "F-004"], **expected},
        }
    )


def _names(reply, **allowances):
    return check_entity_register(reply, world(), _scenario(allowances=allowances), character())


# --- Entity register --------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Vessa sells to the Lantern Guild, not to the Grey Harbour crews.",
        "Ask the Guild. I'm busy.",  # registered alias; a lone sentence opener
        "I don't trade with strangers. Not today, friend.",
        "Coin first. Then we talk, and I'll name my price.",
        "Vessa's cut comes first.",  # possessive of a registered name
    ],
)
def test_registered_names_aliases_and_ordinary_capitals_are_not_flagged(reply):
    result = _names(reply)
    assert result.flagged is False, result.details


@pytest.mark.parametrize(
    ("reply", "names"),
    [
        ("The Ashen Court buys from me.", ["Ashen Court"]),
        ("Talk to Brother Kesh in the market.", ["Brother Kesh"]),
        ("Ask Kesh, or ask Marrow.", ["Kesh", "Marrow"]),
        # Negation needs context: still a flag.
        ("I've never heard of the House of Reeds.", ["House of Reeds"]),
        # Quotation needs context: still a flag.
        ('"Ashen Court"? Never heard of it.', ["Ashen Court"]),
    ],
)
def test_names_outside_the_register_are_flagged(reply, names):
    result = _names(reply)
    assert result.flagged is True
    assert result.details["names"] == names


def test_a_lone_word_opening_a_sentence_is_a_documented_miss():
    # Indistinguishable by rule from "Ask" or "Coin"; the audit samples such misses.
    assert _names("Marrow knows the way.").flagged is False


def test_paraphrase_of_an_unregistered_entity_is_a_documented_miss():
    assert _names("Some monks down by the docks buy from me.").flagged is False


def test_allowed_invention_does_not_excuse_a_name_but_rides_on_the_flag():
    result = _names("Brother Kesh sells bread.", allowed_invention=["minor street vendors"])
    assert result.flagged is True
    assert result.details["allowed_invention"] == ["minor street vendors"]


def test_the_characters_own_name_is_never_unregistered():
    sheet = character().model_copy(update={"name": "Vessa Thorne"})
    result = check_entity_register("I am Vessa Thorne.", world(), _scenario(), sheet)
    assert result.flagged is False


# --- Forbidden facts --------------------------------------------------------------------


def _forbidden(reply, **expected):
    return check_forbidden_facts(reply, world(), _scenario(**expected))


@pytest.mark.parametrize(
    "reply",
    [
        "The route runs through the drowned chapel.",
        "Drowned chapel. That's all you get.",  # leading article not required
        "Take the chapel route at night.",  # alias
        "It does not run through the drowned chapel.",  # negation still flags
        'You heard "the drowned chapel"? Gossip.',  # quotation still flags
    ],
)
def test_forbidden_fact_object_or_alias_is_flagged(reply):
    result = _forbidden(reply)
    assert result.flagged is True
    assert "F-002" in result.details["facts"]


def test_paraphrase_of_a_forbidden_fact_is_a_documented_miss():
    assert _forbidden("Through the sunken church, if you must know.").flagged is False


def test_subject_alone_is_flagged_without_a_permitted_acknowledgement():
    result = _forbidden("The smuggling route? What of it.")
    assert result.flagged is True
    assert result.details["facts"] == {"F-002": ["smuggling route"]}


def test_withholding_with_a_permitted_acknowledgement_is_not_flagged():
    allowances = {"permitted_acknowledgements": ["a route exists"]}
    result = _forbidden("There is a smuggling route. Where it runs is mine.", allowances=allowances)
    assert result.flagged is False


def test_a_permitted_acknowledgement_covers_only_the_target_fact():
    allowances = {"permitted_acknowledgements": ["a route exists"]}
    result = _forbidden("The guild's ledger? Safe enough.", allowances=allowances)
    assert result.details["facts"] == {"F-004": ["guild's ledger"]}


def test_a_permitted_acknowledgement_does_not_excuse_disclosure():
    allowances = {"permitted_acknowledgements": ["a route exists"]}
    result = _forbidden("The smuggling route runs by the drowned chapel.", allowances=allowances)
    assert result.flagged is True


# --- Spoiler facts ----------------------------------------------------------------------


def _spoilers(reply, **expected):
    return check_spoiler_facts(reply, world(), _scenario(**expected))


def test_secret_and_not_yet_known_facts_are_spoiler_flags():
    # F-004 is secret at act-1; a bare "toll" is not F-005's subject.
    result = _spoilers("The ledger hides in the lantern loft, and the toll will double soon.")
    assert set(result.details["facts"]) == {"F-004"}
    # F-005 is not yet known to Vessa until act-2.
    result = _spoilers("The harbour toll will double after the deal.")
    assert result.details["facts"] == {"F-005": ["harbour toll", "deal"]}


def test_facts_the_character_may_state_are_not_spoilers():
    # F-001 is known to Vessa at act-1 and not secret.
    result = _spoilers("Vessa fences goods for the Lantern Guild.")
    assert "F-001" not in result.details["facts"]


def test_a_fact_known_only_later_is_a_spoiler_now():
    # F-003 is known to Vessa only from act-3.
    result = _spoilers("The harbourmaster will turn on them.")
    assert "F-003" in result.details["facts"]


def test_lore_flags_are_pending_unknown():
    verdict = semantic_verdict(_forbidden("Drowned chapel."))
    assert (verdict.check, verdict.verdict, verdict.provenance, verdict.review_status) == (
        "forbidden_facts",
        "unknown",
        None,
        "pending",
    )
    assert verdict.flagged is True


def test_a_missing_reply_is_not_flagged():
    assert _forbidden(None).flagged is None
    assert _spoilers(None).flagged is None
    assert check_entity_register(None, world(), _scenario(), character()).flagged is None


@pytest.mark.parametrize("reply", ["Of practice.", "The of practice.", "Of", "The"])
def test_connector_only_sentence_openers_are_not_entity_names(reply):
    result = _names(reply)
    assert result.flagged is False
