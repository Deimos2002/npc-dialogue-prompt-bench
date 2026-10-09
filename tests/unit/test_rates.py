import pytest

from npcbench.metrics.rates import Rate, rates_by, verdict_rates_by


def test_rate_reports_k_over_n():
    rate = Rate(3, 10)
    assert str(rate) == "3/10"
    assert rate.value == pytest.approx(0.3)


def test_zero_denominator_has_no_value():
    assert Rate(0, 0).value is None


def test_k_cannot_exceed_n():
    with pytest.raises(ValueError):
        Rate(3, 2)


def test_rates_by_group():
    items = [("a", True), ("a", False), ("b", True)]
    out = rates_by(items, key=lambda x: x[0], hit=lambda x: x[1])
    assert out == {"a": Rate(1, 2), "b": Rate(1, 1)}


def test_verdict_rates_by_group_count_fails_over_decided_verdicts():
    items = [("a", "fail"), ("a", "pass"), ("a", "unknown"), ("b", "unknown")]
    out = verdict_rates_by(items, key=lambda x: x[0], verdict=lambda x: x[1])
    assert {group: rate.as_dict() for group, rate in out.items()} == {
        "a": {"k": 1, "n": 2, "unknown": 1},
        "b": {"k": 0, "n": 0, "unknown": 1},
    }
