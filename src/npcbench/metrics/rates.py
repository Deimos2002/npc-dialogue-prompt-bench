"""Rates always carry their counts (protocol)."""

from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass

from npcbench.schemas import VerdictValue


@dataclass(frozen=True)
class Rate:
    k: int
    n: int

    def __post_init__(self) -> None:
        if self.k < 0 or self.n < 0 or self.k > self.n:
            raise ValueError(f"Invalid rate {self.k}/{self.n}")

    @property
    def value(self) -> float | None:
        return None if self.n == 0 else self.k / self.n

    def as_dict(self) -> dict[str, int]:
        return {"k": self.k, "n": self.n}

    def __str__(self) -> str:
        return f"{self.k}/{self.n}"


def rates_by[T](
    items: Iterable[T], *, key: Callable[[T], Hashable], hit: Callable[[T], bool]
) -> dict[Hashable, Rate]:
    counts: dict[Hashable, list[int]] = {}
    for item in items:
        bucket = counts.setdefault(key(item), [0, 0])
        bucket[0] += int(bool(hit(item)))
        bucket[1] += 1
    return {group: Rate(k, n) for group, (k, n) in counts.items()}


@dataclass(frozen=True)
class VerdictRate:
    """A fail rate over decided verdicts; `unknown` verdicts are counted but never in `n`."""

    rate: Rate
    unknown: int

    def as_dict(self) -> dict[str, int]:
        return {**self.rate.as_dict(), "unknown": self.unknown}


def verdict_rate(verdicts: Iterable[VerdictValue]) -> VerdictRate:
    k = n = unknown = 0
    for verdict in verdicts:
        if verdict == "unknown":
            unknown += 1
        else:
            n += 1
            k += verdict == "fail"
    return VerdictRate(Rate(k, n), unknown)


def verdict_rates_by[T](
    items: Iterable[T], *, key: Callable[[T], Hashable], verdict: Callable[[T], VerdictValue]
) -> dict[Hashable, VerdictRate]:
    groups: dict[Hashable, list[VerdictValue]] = {}
    for item in items:
        groups.setdefault(key(item), []).append(verdict(item))
    return {group: verdict_rate(values) for group, values in groups.items()}


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k/n (95% by default); None when n is 0."""
    if n == 0:
        return None
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))
