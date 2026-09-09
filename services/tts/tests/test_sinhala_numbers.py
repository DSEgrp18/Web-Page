"""Sinhala cardinal number forms.

Every expected value here is a claim about Sinhala, not about code, so this file
is the one a native speaker reads. **Reviewed and confirmed by the project owner
on 2026-09-09.**

That settles the spelling. It does not settle pronunciation: the checkpoint was
fine-tuned on romanised ASCII, so a correctly written numeral can still be
spoken badly, and only listening will tell. If a number ever sounds wrong,
correcting the table in ``sinhala_numbers.py`` fixes every number that uses it,
and the failure here will name exactly which.
"""

from __future__ import annotations

import pytest

from sinhala_tts.sinhala_numbers import (
    MAX_SUPPORTED,
    NumberOutOfRangeError,
    cardinal,
    digits_individually,
)


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "බින්දුව"),
        (1, "එක"),
        (2, "දෙක"),
        (5, "පහ"),
        (9, "නවය"),
    ],
)
def test_units(number: int, expected: str) -> None:
    assert cardinal(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (10, "දහය"),
        (11, "එකොළහ"),
        (12, "දොළහ"),
        (15, "පහළොව"),
        (19, "දහනවය"),
    ],
)
def test_teens_are_irregular(number: int, expected: str) -> None:
    """10-19 are listed individually because they are not composed regularly."""
    assert cardinal(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (20, "විස්ස"),
        (30, "තිහ"),
        (50, "පනහ"),
        (70, "හැත්තෑව"),
        (90, "අනූව"),
    ],
)
def test_round_tens_use_the_standalone_form(number: int, expected: str) -> None:
    assert cardinal(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (21, "විසි එක"),
        (24, "විසි හතර"),
        (42, "හතළිස් දෙක"),
        (55, "පනස් පහ"),
        (75, "හැත්තෑ පහ"),
        (99, "අනූ නවය"),
    ],
)
def test_tens_switch_to_the_combining_form_before_a_unit(number: int, expected: str) -> None:
    """විස්ස alone, but විසි in විසි එක. This is the pattern most at risk of
    being got wrong, so it is tested across the whole range of tens."""
    assert cardinal(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (100, "සියය"),
        (200, "දෙසියය"),
        (999, "නවසිය අනූ නවය"),
        (101, "එකසිය එක"),
        (125, "එකසිය විසි පහ"),
        (350, "තුන්සිය පනහ"),
    ],
)
def test_hundreds(number: int, expected: str) -> None:
    assert cardinal(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1000, "දහස"),
        (1500, "එක්දහස් පන්සියය"),
        (2024, "දෙදහස් විසි හතර"),
        (2026, "දෙදහස් විසි හය"),
        (9999, "නවදහස් නවසිය අනූ නවය"),
    ],
)
def test_thousands(number: int, expected: str) -> None:
    assert cardinal(number) == expected


def test_a_year_reads_as_a_cardinal() -> None:
    """Years are the most common number in a textbook, and read as cardinals."""
    assert cardinal(2024) == "දෙදහස් විසි හතර"


# --------------------------------------------------------------------------
# Range
# --------------------------------------------------------------------------


def test_every_supported_number_produces_words() -> None:
    """No gap in the tables, checked exhaustively rather than by sampling.

    A missing key would raise KeyError deep inside composition, and would only
    show up when a reader happened to open a page containing that number.
    """
    for n in range(MAX_SUPPORTED + 1):
        words = cardinal(n)
        assert words, f"{n} produced empty text"
        assert not words.startswith(" ") and not words.endswith(" "), n
        assert "  " not in words, f"{n} produced a double space: {words!r}"


@pytest.mark.parametrize("number", [10000, 123456, -1])
def test_out_of_range_raises_rather_than_guessing(number: int) -> None:
    """Refusing is the point.

    A wrong Sinhala form would sound correct and would be far harder to notice
    than the digit deletion this module exists to fix.
    """
    with pytest.raises(NumberOutOfRangeError):
        cardinal(number)


# --------------------------------------------------------------------------
# Digit-by-digit reading
# --------------------------------------------------------------------------


def test_digits_individually() -> None:
    assert digits_individually("42") == "හතර දෙක"
    assert digits_individually("305") == "තුන බින්දුව පහ"


def test_digits_individually_handles_leading_zeros() -> None:
    assert digits_individually("007") == "බින්දුව බින්දුව හත"
