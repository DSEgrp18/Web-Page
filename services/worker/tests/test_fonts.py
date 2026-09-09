"""Legacy Sinhala font identification.

The stakes are asymmetric and the tests are written accordingly. Missing a
legacy font means narrating Latin gibberish as though it were the book, which
nothing downstream can detect. Flagging a Unicode font by mistake means
withholding a page that was perfectly readable — bad, but announced.
"""

from __future__ import annotations

import pytest

from sinhala_documents.fonts import (
    identify_legacy_font,
    looks_like_legacy_text,
    non_ascii_ratio,
    normalise_font_name,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FMAbhaya", "fmabhaya"),
        ("ABCDEF+FMAbhaya", "fmabhaya"),
        ("ABCDEF+FM-Abhaya-Bold", "fmabhaya"),
        ("FMAbhaya,Italic", "fmabhaya"),
        ("ABCDEF+TimesNewRomanPSMT", "timesnewroman"),
        ("", ""),
    ],
)
def test_font_names_reduce_to_a_family(raw: str, expected: str) -> None:
    """A subset prefix and a style suffix must not hide a font's identity."""
    assert normalise_font_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["FMAbhaya", "ABCDEF+FMAbhaya", "FM-Abhaya-Bold", "FMBindumathi", "DL-Manel", "Kaputa"],
)
def test_legacy_fonts_are_identified(raw: str) -> None:
    assert identify_legacy_font(raw) is not None


@pytest.mark.parametrize(
    "raw",
    [
        "NotoSansSinhala",
        "Iskoola Pota",
        "ABCDEF+TimesNewRomanPSMT",
        "Helvetica",
        "",
        # Names that begin like a legacy family but announce Unicode. A false
        # positive here withholds a page that reads perfectly well.
        "FMMalithiUnicode",
        "DLManelUnicode",
    ],
)
def test_unicode_fonts_are_left_alone(raw: str) -> None:
    assert identify_legacy_font(raw) is None


def test_only_fm_abhaya_is_marked_convertible() -> None:
    """CLAUDE.md forbids applying one family's table to another.

    A wrong mapping does not fail loudly. It produces fluent Sinhala saying
    something the author never wrote, which no automated check can catch.
    """
    assert identify_legacy_font("FMAbhaya").convertible is True
    assert identify_legacy_font("DL-Manel").convertible is False


# --------------------------------------------------------------------------
# The second, weaker signal
# --------------------------------------------------------------------------


def test_legacy_text_shape_is_recognised_without_the_font_name() -> None:
    assert looks_like_legacy_text("fmdñl mßiaÑ;h yd tu ldrKh ù we;")


@pytest.mark.parametrize(
    "text",
    [
        "පොත් කියවීම මගින් දැනුම වර්ධනය වේ.",
        "This is an ordinary English sentence about reading.",
        "poth kiyaviima magin dhaenuma vardhanaya vee.",
        "",
        "café",  # too short for the ratio to mean anything
    ],
)
def test_ordinary_text_is_not_suspected(text: str) -> None:
    assert not looks_like_legacy_text(text)


def test_the_ratio_ignores_whitespace() -> None:
    assert non_ascii_ratio("   ") == 0.0
    assert non_ascii_ratio("ab") == 0.0
    assert non_ascii_ratio("ñb") == 0.5
