from npcbench.checks.base import mechanical_verdict
from npcbench.checks.overplay import check_overplay
from npcbench.schemas import OverplayLimits

LIMITS = OverplayLimits(max_words=5, tics=["mark my words", "friend"], max_tics=1)


def test_within_limits_is_not_flagged():
    result = check_overplay("Fine goods, friend.", LIMITS)
    assert not result.flagged
    assert result.details == {"words": 3, "tics": 1, "reasons": []}


def test_reply_over_length_budget_is_flagged():
    result = check_overplay("one two three four five six", LIMITS)
    assert result.flagged
    assert result.details["reasons"] == ["length"]


def test_reply_over_tic_cap_is_flagged():
    result = check_overplay("Friend, mark my words, friend.", LIMITS)
    assert result.flagged
    assert result.details["tics"] == 3
    assert result.details["reasons"] == ["tics"]


def test_tics_match_whole_phrases_case_insensitively():
    assert check_overplay("Friendly folk.", LIMITS).details["tics"] == 0
    assert check_overplay("MARK MY WORDS.", LIMITS).details["tics"] == 1


def test_overlapping_tics_count_the_longest_match_once():
    limits = OverplayLimits(max_words=50, tics=["aye", "aye aye"], max_tics=5)
    assert check_overplay("Aye aye, captain.", limits).details["tics"] == 1
    assert check_overplay("Aye aye aye.", limits).details["tics"] == 2


def test_longest_match_wins_whatever_the_list_order():
    limits = OverplayLimits(max_words=50, tics=["my words", "mark my words"], max_tics=5)
    assert check_overplay("Mark my words.", limits).details["tics"] == 1


def test_tic_phrases_match_across_any_whitespace():
    assert check_overplay("Mark  my\nwords.", LIMITS).details["tics"] == 1


def test_quoted_tics_still_count():
    result = check_overplay('You said "friend"? Friend, mark my words.', LIMITS)
    assert result.details["tics"] == 3


def test_empty_reply_is_not_flagged():
    result = check_overplay("", LIMITS)
    assert not result.flagged
    assert result.details["words"] == 0


def test_overplay_verdict_is_its_flag():
    passed = mechanical_verdict(check_overplay("Fine goods, friend.", LIMITS))
    failed = mechanical_verdict(check_overplay("one two three four five six", LIMITS))
    assert (passed.check, passed.verdict, passed.provenance, passed.review_status) == (
        "overplay",
        "pass",
        "mechanical",
        "complete",
    )
    assert (failed.verdict, failed.flagged) == ("fail", True)


def test_a_missing_reply_cannot_be_evaluated_and_is_unknown():
    result = check_overplay(None, LIMITS)
    assert result.flagged is None
    verdict = mechanical_verdict(result)
    assert (verdict.verdict, verdict.provenance, verdict.review_status) == (
        "unknown",
        "mechanical",
        "complete",
    )
