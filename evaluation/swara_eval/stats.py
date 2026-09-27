"""The statistics the protocol names, small enough to check by hand.

Plain Python, seeded, and tested against worked examples, so a result in the
dissertation can be traced to a function a reader can read in one sitting.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Estimate:
    """A point estimate with a percentile bootstrap interval."""

    value: float
    low: float
    high: float
    n: int

    def as_dict(self) -> dict[str, float | int | None]:
        """JSON has no NaN: an estimate from no data is reported as null."""

        def finite(x: float) -> float | None:
            return None if math.isnan(x) else round(x, 4)

        return {
            "value": finite(self.value),
            "low": finite(self.low),
            "high": finite(self.high),
            "n": self.n,
        }


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def bootstrap(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = mean,
    *,
    resamples: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> Estimate:
    """Percentile bootstrap. Seeded, so the same data gives the same interval."""
    if not values:
        return Estimate(math.nan, math.nan, math.nan, 0)
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(
        statistic([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)
    )
    tail = (1 - level) / 2
    return Estimate(
        value=statistic(values),
        low=percentile(draws, tail * 100),
        high=percentile(draws, (1 - tail) * 100),
        n=n,
    )


def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks, as numpy's default does."""
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    below = math.floor(position)
    above = math.ceil(position)
    if below == above:
        return float(ordered[below])
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)


def krippendorff_alpha_nominal(units: Sequence[Sequence[Hashable | None]]) -> float:
    """Krippendorff's alpha for nominal ratings.

    ``units`` holds one row per rated item, one entry per rater, ``None`` where
    a rater did not rate it. Items rated by fewer than two raters are ignored,
    as the coefficient requires.
    """
    coincidence: Counter[tuple[Hashable, Hashable]] = Counter()
    for unit in units:
        values = [v for v in unit if v is not None]
        m = len(values)
        if m < 2:
            continue
        for i, a in enumerate(values):
            for j, b in enumerate(values):
                if i != j:
                    coincidence[(a, b)] += 1 / (m - 1)
    totals: Counter[Hashable] = Counter()
    for (a, _), weight in coincidence.items():
        totals[a] += weight
    n = sum(totals.values())
    if n <= 1:
        return math.nan
    observed = sum(w for (a, b), w in coincidence.items() if a != b)
    expected = sum(totals[a] * totals[b] for a in totals for b in totals if a != b) / (n - 1)
    if expected == 0:
        return 1.0
    return 1 - observed / expected


def binomial_two_sided(successes: int, trials: int, p: float = 0.5) -> float:
    """Exact two-sided binomial test: the chance of a split at least this uneven."""
    if trials == 0:
        return 1.0

    def pmf(k: int) -> float:
        return math.comb(trials, k) * p**k * (1 - p) ** (trials - k)

    observed = pmf(successes)
    return min(1.0, sum(pmf(k) for k in range(trials + 1) if pmf(k) <= observed * (1 + 1e-9)))


def umux_lite(capabilities: int, ease: int) -> float:
    """UMUX-Lite on 0–100 from its two seven-point items (Lewis et al., 2013).

    The Sinhala translation used in the study has not been validated; any
    result reports that alongside the score.
    """
    for item in (capabilities, ease):
        if not 1 <= item <= 7:
            raise ValueError("UMUX-Lite items are on a 1–7 scale.")
    return ((capabilities - 1) + (ease - 1)) / 12 * 100
