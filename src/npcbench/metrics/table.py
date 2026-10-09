"""The arm × model metrics table with a family cluster bootstrap (protocol).

Families are the resampling unit (GLOSSARY: Family): each resample draws whole families
with replacement, keeping their turns, spoiler pairs, arms, models and replicates together.
Every cell is computed on the same draws, so arm differences on one model stay paired.
Intervals are 95% percentile intervals; they describe uncertainty and are not
significance tests.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np

from npcbench.schemas import Provenance, VerdictValue

DEFAULT_RESAMPLES = 2000
LEVEL = 0.95
# A stratum with fewer families than this is descriptive, however many replies it holds.
MIN_FAMILIES = 10

Cell = tuple[str, str, str]  # metric, arm, model
ALL_CLASSES = "all"
PENDING = "review pending"
# protocol: plan_in_character versus direct is the predeclared primary comparison.
PRIMARY = frozenset({"plan_in_character", "direct"})


@dataclass(frozen=True)
class MetricRow:
    """One reply's outcome on one metric."""

    family: str
    class_: str
    arm: str
    model: str
    metric: str
    verdict: VerdictValue
    # Absent while review is pending (GLOSSARY: Provenance).
    provenance: Provenance | None
    scenario_id: str
    replicate: int = 0
    turn_index: int = 0


def _family_counts_by_cell(
    rows: Iterable[MetricRow], families: list[str]
) -> dict[Cell, tuple[np.ndarray, np.ndarray]]:
    index = {f: i for i, f in enumerate(families)}
    counts: dict[Cell, tuple[np.ndarray, np.ndarray]] = {}
    for row in rows:
        cell = (row.metric, row.arm, row.model)
        k, n = counts.setdefault(cell, (np.zeros(len(families)), np.zeros(len(families))))
        if row.verdict != "unknown":
            n[index[row.family]] += 1
            k[index[row.family]] += row.verdict == "fail"
    return counts


def _weights(n_families: int, seed: int, resamples: int) -> np.ndarray:
    """How often each family appears in each resample: shape (resamples, families)."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_families, size=(resamples, n_families))
    weights = np.zeros((resamples, n_families))
    np.add.at(weights, (np.arange(resamples)[:, None], draws), 1)
    return weights


def _resampled(k: np.ndarray, n: np.ndarray, weights: np.ndarray) -> np.ndarray:
    fails, decided = weights @ k, weights @ n
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(decided > 0, fails / decided, np.nan)


def bootstrap_rates(
    rows: list[MetricRow], *, seed: int, resamples: int = DEFAULT_RESAMPLES
) -> dict[Cell, np.ndarray]:
    """Each cell's fail rate in every resample (NaN where a resample decided nothing)."""
    families = sorted({r.family for r in rows})
    weights = _weights(len(families), seed, resamples)
    return {
        cell: _resampled(k, n, weights)
        for cell, (k, n) in _family_counts_by_cell(rows, families).items()
    }


def _interval(samples: np.ndarray) -> list[float] | None:
    if np.all(np.isnan(samples)):
        return None
    tail = (1 - LEVEL) / 2 * 100
    low, high = np.nanpercentile(samples, [tail, 100 - tail])
    return [float(low), float(high)]


def _provenance_mix(rows: Iterable[MetricRow]) -> dict[str, int]:
    return dict(sorted(Counter(r.provenance or PENDING for r in rows).items()))


def _strategy(arm_id: str) -> str:
    return arm_id.split("@", 1)[0]


def family_counts(family_classes: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Distinct families per class and overall; a family spanning classes counts once overall."""
    pairs = set(family_classes)
    by_class: dict[str, int] = Counter(cls for _, cls in pairs)
    return {
        "by_class": dict(sorted(by_class.items())),
        "unique": len({family for family, _ in pairs}),
    }


def arm_model_table(
    rows: list[MetricRow], *, seed: int, resamples: int = DEFAULT_RESAMPLES
) -> dict[str, Any]:
    families = sorted({r.family for r in rows})
    weights = _weights(len(families), seed, resamples)
    counts = _family_counts_by_cell(rows, families)

    cells = []
    for cell in sorted(counts):
        metric, arm, model = cell
        in_cell = [r for r in rows if (r.metric, r.arm, r.model) == cell]
        strata = [ALL_CLASSES, *sorted({r.class_ for r in in_cell})]
        for cls in strata:
            stratum = [r for r in in_cell if cls in (ALL_CLASSES, r.class_)]
            k, n = _family_counts_by_cell(stratum, families)[cell]
            cells.append(
                {
                    "metric": metric,
                    "arm": arm,
                    "model": model,
                    "class": cls,
                    "k": int(k.sum()),
                    "n": int(n.sum()),
                    "unknown": sum(r.verdict == "unknown" for r in stratum),
                    "interval": _interval(_resampled(k, n, weights)),
                    "provenance": _provenance_mix(stratum),
                    "families": len({r.family for r in stratum}),
                    "descriptive": int(np.count_nonzero(n)) < MIN_FAMILIES,
                }
            )

    differences = []
    for metric, model in sorted({(m, mo) for m, _, mo in counts}):
        arms = sorted(a for m, a, mo in counts if (m, mo) == (metric, model))
        for first, second in combinations(arms, 2):
            observations = {}
            for row in rows:
                if (row.metric, row.model) != (metric, model) or row.arm not in (first, second):
                    continue
                key = (row.scenario_id, row.replicate, row.turn_index)
                pair = observations.setdefault(key, {})
                if row.arm in pair:
                    raise ValueError(f"Duplicate observation {key} for arm {row.arm}")
                pair[row.arm] = row
            matched = []
            for pair in observations.values():
                if first not in pair or second not in pair:
                    continue
                a, b = pair[first], pair[second]
                if a.family != b.family:
                    raise ValueError("Matched observations must belong to the same family")
                if a.verdict != "unknown" and b.verdict != "unknown":
                    matched.extend((a, b))
            if not matched:
                continue
            paired_counts = _family_counts_by_cell(matched, families)
            k1, n1 = paired_counts[(metric, first, model)]
            k2, n2 = paired_counts[(metric, second, model)]
            paired = _resampled(k1, n1, weights) - _resampled(k2, n2, weights)
            shared = int(np.count_nonzero(n1))
            arm_rows = {
                arm: [r for r in rows if (r.metric, r.model, r.arm) == (metric, model, arm)]
                for arm in (first, second)
            }
            differences.append(
                {
                    "metric": metric,
                    "model": model,
                    "arm": first,
                    "versus": second,
                    "primary": {_strategy(first), _strategy(second)} == PRIMARY,
                    "unknown": {
                        arm: sum(r.verdict == "unknown" for r in arm_rows[arm]) for arm in arm_rows
                    },
                    "provenance": {arm: _provenance_mix(arm_rows[arm]) for arm in arm_rows},
                    "difference": float(k1.sum() / n1.sum() - k2.sum() / n2.sum()),
                    "interval": _interval(paired),
                    "families": shared,
                    "descriptive": shared < MIN_FAMILIES,
                }
            )

    return {
        "bootstrap": {"seed": seed, "resamples": resamples, "unit": "family", "level": LEVEL},
        "arm_model": cells,
        "paired_differences": differences,
    }
