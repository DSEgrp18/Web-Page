"""The statistics, against worked examples from their sources."""

from __future__ import annotations

import math

import pytest

from swara_eval.stats import (
    binomial_two_sided,
    bootstrap,
    krippendorff_alpha_nominal,
    percentile,
    umux_lite,
)


def test_krippendorffs_own_nominal_example_gives_0_743() -> None:
    # Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability", §C:
    # four observers, twelve units, nominal data.
    a = [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None]
    b = [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3]
    c = [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None]
    d = [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]
    units = list(zip(a, b, c, d, strict=True))

    assert krippendorff_alpha_nominal(units) == pytest.approx(0.743, abs=0.001)


def test_perfect_agreement_is_one() -> None:
    assert krippendorff_alpha_nominal([("g", "g"), ("u", "u"), ("g", "g")]) == 1.0


def test_percentile_matches_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 10.0]

    assert percentile(values, 50) == 3.0
    assert percentile(values, 95) == pytest.approx(8.8)


def test_the_exact_sign_test() -> None:
    # 9 of 10 one way: 2 * (1 + 10) / 1024.
    assert binomial_two_sided(9, 10) == pytest.approx(22 / 1024)
    assert binomial_two_sided(5, 10) == pytest.approx(1.0)


def test_umux_lite_runs_from_0_to_100() -> None:
    assert umux_lite(1, 1) == 0
    assert umux_lite(7, 7) == 100
    with pytest.raises(ValueError):
        umux_lite(0, 4)


def test_the_bootstrap_is_seeded_and_brackets_the_mean() -> None:
    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0]

    first, second = bootstrap(values), bootstrap(values)

    assert first == second
    assert first.low <= first.value == 0.75 <= first.high


def test_no_data_is_reported_as_null_not_nan() -> None:
    estimate = bootstrap([])

    assert math.isnan(estimate.value)
    assert estimate.as_dict() == {"value": None, "low": None, "high": None, "n": 0}
