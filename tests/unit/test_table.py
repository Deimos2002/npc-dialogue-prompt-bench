"""The arm × model metrics table and its family bootstrap (protocol)."""

import numpy as np
import pytest

from npcbench.metrics.table import (
    MetricRow,
    arm_model_table,
    bootstrap_rates,
    family_counts,
)


def _row(
    family,
    arm,
    verdict,
    *,
    metric="overplay",
    cls="on_script",
    model="m1",
    prov="mechanical",
    turn=0,
):
    return MetricRow(
        scenario_id=family,
        turn_index=turn,
        family=family,
        class_=cls,
        arm=arm,
        model=model,
        metric=metric,
        verdict=verdict,
        provenance=prov,
    )


def _rows(arm, fails_by_family, per_family=4, **kw):
    rows = []
    for family, fails in fails_by_family.items():
        rows += [_row(family, arm, "fail", turn=i, **kw) for i in range(fails)]
        rows += [_row(family, arm, "pass", turn=i, **kw) for i in range(fails, per_family)]
    return rows


def test_the_bootstrap_resamples_whole_families_and_is_seeded():
    # Family A always fails, family B never does: a resample can only mix whole families.
    rows = _rows("direct@v1", {"A": 4, "B": 0})
    rates = bootstrap_rates(rows, seed=1, resamples=500)[("overplay", "direct@v1", "m1")]
    assert set(np.round(rates, 6)) <= {0.0, 0.5, 1.0}
    again = bootstrap_rates(rows, seed=1, resamples=500)[("overplay", "direct@v1", "m1")]
    other = bootstrap_rates(rows, seed=2, resamples=500)[("overplay", "direct@v1", "m1")]
    assert np.array_equal(rates, again)
    assert not np.array_equal(rates, other)


def test_cells_carry_counts_interval_unknowns_and_provenance_mix():
    rows = _rows("direct@v1", {"A": 1, "B": 0}, prov="adjudicated", metric="collapse")
    rows.append(_row("A", "direct@v1", "unknown", metric="collapse", prov=None))
    rows.append(_row("B", "direct@v1", "fail", metric="collapse", prov="adjudicated"))
    table = arm_model_table(rows, seed=0, resamples=200)
    (cell,) = [c for c in table["arm_model"] if c["class"] == "all"]
    assert (cell["metric"], cell["arm"], cell["model"]) == ("collapse", "direct@v1", "m1")
    assert (cell["k"], cell["n"], cell["unknown"]) == (2, 9, 1)
    # Provenance is absent while review is pending (GLOSSARY: Provenance).
    assert cell["provenance"] == {"adjudicated": 9, "review pending": 1}
    assert cell["families"] == 2
    low, high = cell["interval"]
    assert 0 <= low <= 2 / 9 <= high <= 1
    assert cell["descriptive"] is True  # fewer than 10 families


def test_a_stratum_with_enough_families_is_not_marked_descriptive():
    rows = _rows("direct@v1", {f"F{i}": i % 2 for i in range(12)})
    table = arm_model_table(rows, seed=0, resamples=200)
    (cell,) = [c for c in table["arm_model"] if c["class"] == "all"]
    assert (cell["families"], cell["descriptive"]) == (12, False)


def test_paired_differences_use_the_same_family_draws_for_both_arms():
    same = {f"F{i}": i % 3 for i in range(12)}
    rows = _rows("direct@v1", same) + _rows("plan_generic@v1", same)
    (diff,) = arm_model_table(rows, seed=0, resamples=300)["paired_differences"]
    assert (diff["metric"], diff["model"]) == ("overplay", "m1")
    assert (diff["arm"], diff["versus"]) == ("direct@v1", "plan_generic@v1")
    # Identical arms on identical families: every paired resample differs by exactly 0.
    assert diff["difference"] == 0
    assert diff["interval"] == pytest.approx([0.0, 0.0])


def test_a_real_difference_shows_in_the_paired_interval():
    rows = _rows("direct@v1", {f"F{i}": 3 for i in range(12)})
    rows += _rows("plan_generic@v1", {f"F{i}": 1 for i in range(12)})
    (diff,) = arm_model_table(rows, seed=0, resamples=300)["paired_differences"]
    assert diff["difference"] == pytest.approx(0.5)
    assert diff["interval"] == pytest.approx([0.5, 0.5])


def test_families_are_counted_per_class_and_once_overall():
    families = family_counts([("F1", "spoiler"), ("F1", "adversarial"), ("F2", "spoiler")])
    assert families == {"by_class": {"adversarial": 1, "spoiler": 2}, "unique": 2}


def test_the_table_records_its_bootstrap_scheme():
    table = arm_model_table(_rows("direct@v1", {"A": 1}), seed=3, resamples=100)
    assert table["bootstrap"] == {"seed": 3, "resamples": 100, "unit": "family", "level": 0.95}


def test_disjoint_decided_observations_do_not_produce_a_paired_difference():
    rows = [
        _row("F1", "a", "fail"),
        _row("F1", "b", "unknown"),
        _row("F2", "a", "unknown"),
        _row("F2", "b", "pass"),
    ]
    assert arm_model_table(rows, seed=0)["paired_differences"] == []


def test_pairing_matches_turn_and_replicate_and_excludes_unknowns():
    rows = [
        _row("F1", "a", "fail", turn=0),
        _row("F1", "b", "unknown", turn=0),
        _row("F1", "a", "pass", turn=1),
        _row("F1", "b", "pass", turn=1),
        _row("F1", "a", "fail", turn=2),
        _row("F1", "b", "pass", turn=3),
    ]
    from dataclasses import replace

    rows += [
        replace(_row("F1", "a", "fail", turn=4), replicate=0),
        replace(_row("F1", "b", "pass", turn=4), replicate=1),
    ]
    (diff,) = arm_model_table(rows, seed=0)["paired_differences"]
    assert diff["difference"] == 0
    assert diff["interval"] == [0, 0]
    assert diff["families"] == 1


def test_different_scenarios_in_one_family_are_not_matched():
    from dataclasses import replace

    rows = [_row("F", "a", "fail"), replace(_row("F", "b", "pass"), scenario_id="other")]
    assert arm_model_table(rows, seed=0)["paired_differences"] == []


def test_each_class_is_its_own_stratum_and_small_strata_are_descriptive():
    rows = _rows("direct@v1", {f"F{i}": i % 2 for i in range(12)})
    rows += _rows("direct@v1", {"S1": 1}, cls="spoiler")
    table = arm_model_table(rows, seed=0, resamples=100)
    cells = {c["class"]: c for c in table["arm_model"]}
    assert set(cells) == {"all", "on_script", "spoiler"}
    assert (cells["spoiler"]["k"], cells["spoiler"]["n"]) == (1, 4)
    assert cells["spoiler"]["descriptive"] is True
    assert cells["on_script"]["descriptive"] is False
    assert cells["all"]["n"] == 52


def test_paired_differences_show_unknowns_provenance_and_the_primary_comparison():
    rows = []
    for i in range(12):
        rows += [
            _row(f"F{i}", "direct@v1", "fail", turn=0),
            _row(f"F{i}", "plan_in_character@v1", "pass", turn=0),
            _row(f"F{i}", "plan_generic@v1", "pass", turn=0),
        ]
    rows.append(_row("F0", "direct@v1", "unknown", turn=1, prov=None))
    diffs = arm_model_table(rows, seed=0, resamples=100)["paired_differences"]
    by_arms = {(d["arm"], d["versus"]): d for d in diffs}
    primary = by_arms[("direct@v1", "plan_in_character@v1")]
    assert primary["primary"] is True
    assert primary["unknown"] == {"direct@v1": 1, "plan_in_character@v1": 0}
    assert primary["provenance"]["direct@v1"] == {"mechanical": 12, "review pending": 1}
    assert by_arms[("direct@v1", "plan_generic@v1")]["primary"] is False
