"""Detecting a reading order that flattened extraction has probably scrambled.

The false-positive cost is a page needlessly marked uncertain. The false-
negative cost is a page of interleaved columns narrated as though it were
prose — fluent, confident, and meaningless. The tests below spend most of their
effort on the shapes that must *not* trigger, because that is what makes the
flag worth listening to.
"""

from __future__ import annotations

from sinhala_documents.layout import find_gutter, suspects_multiple_columns

PAGE_WIDTH = 612.0


def block(x: float, top: float, count: int, *, width: float = 7.0, rows: int = 1) -> list[dict]:
    """``count`` characters per row, ``rows`` rows, starting at ``x``/``top``."""
    return [
        {
            "x0": x + column * width,
            "x1": x + (column + 1) * width,
            "top": top + row * 16.0,
            "bottom": top + row * 16.0 + 12.0,
        }
        for row in range(rows)
        for column in range(count)
    ]


def test_two_columns_of_prose_are_detected() -> None:
    chars = block(60, 100, 20, rows=12) + block(340, 100, 20, rows=12)
    assert suspects_multiple_columns(chars, PAGE_WIDTH)


def test_a_full_width_paragraph_is_not_columns() -> None:
    assert not suspects_multiple_columns(block(60, 100, 70, rows=12), PAGE_WIDTH)


def test_a_short_line_leaving_a_wide_right_margin_is_not_columns() -> None:
    """The commonest false positive: the empty half of a page is not a gutter."""
    chars = block(60, 100, 25, rows=12)
    assert not suspects_multiple_columns(chars, PAGE_WIDTH)


def test_a_caption_beside_a_figure_is_not_columns() -> None:
    """Text on both sides of a gap, but not running alongside each other."""
    chars = block(60, 100, 30, rows=2) + block(340, 600, 30, rows=2)
    assert not suspects_multiple_columns(chars, PAGE_WIDTH)


def test_a_centred_heading_over_a_body_is_not_columns() -> None:
    chars = block(200, 80, 12, rows=1) + block(60, 140, 70, rows=10)
    assert not suspects_multiple_columns(chars, PAGE_WIDTH)


def test_a_nearly_empty_page_makes_no_claim() -> None:
    assert not suspects_multiple_columns(block(60, 100, 4), PAGE_WIDTH)
    assert not suspects_multiple_columns([], PAGE_WIDTH)


def test_ordinary_word_spacing_is_not_a_gutter() -> None:
    """Word gaps are a few points; the minimum gutter is far wider."""
    chars: list[dict] = []
    for word in range(14):
        chars += block(60 + word * 40, 100, 4, rows=12)
    assert find_gutter(chars, PAGE_WIDTH) is None


def test_the_margins_themselves_are_never_the_gutter() -> None:
    """Every page has two. Only the middle band is searched."""
    gutter = find_gutter(block(60, 100, 70, rows=12), PAGE_WIDTH)
    assert gutter is None
