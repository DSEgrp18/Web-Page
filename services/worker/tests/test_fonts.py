"""Legacy Sinhala font identification.

The stakes are asymmetric and the tests are written accordingly. Missing a
legacy font means narrating Latin gibberish as though it were the book, which
nothing downstream can detect. Flagging a Unicode font by mistake means
withholding a page that was perfectly readable — bad, but announced.
"""

from __future__ import annotations

import pytest

from sinhala_documents.fonts import (
    SUSPICIOUS_INTERIOR_CAPITAL_RATIO,
    SUSPICIOUS_NON_ASCII_RATIO,
    font_encoding_looks_wrong,
    identify_legacy_font,
    interior_capital_ratio,
    is_unreadable_script,
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


# --------------------------------------------------------------------------
# What a real book turned up
#
# A 168-page Grade 11 Sinhala history textbook, the first real document this
# was run against. Every case below is a font that actually appears in it.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "GMVCDK+FMAbhaya",  # the body text, eight subsets of it
        "RFWEJF+FMAbabldBold",  # the headings
    ],
)
def test_every_legacy_sinhala_font_in_a_real_textbook_is_identified(raw: str) -> None:
    assert identify_legacy_font(raw) is not None


@pytest.mark.parametrize("raw", ["GXVJKP+SHREE-TAM7-1316", "XNEONE+Baamini-Plain"])
def test_legacy_fonts_for_other_languages_are_not_catalogued(raw: str) -> None:
    """The same book sets Tamil in legacy fonts. This reader does not serve Tamil.

    Keeping a catalogue of them would promise support that does not exist, so
    the font names are not recognised. Their text is withheld by
    :func:`is_unreadable_script`, which needs no list — see below.
    """
    assert identify_legacy_font(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "PYOVBT+TimesNewRomanPSMT",  # the English translation of the inscription
        "GUBBPN+MinionPro-Regular",  # the printed roman page numbers
        "XCYJHL+Wingdings-Regular",  # bullet glyphs
        "MSETOK+Calibri",
        "NJHFII+ArialMT",
    ],
)
def test_the_readable_fonts_in_that_book_are_left_alone(raw: str) -> None:
    assert identify_legacy_font(raw) is None


def test_a_suspected_variant_is_reported_without_being_decoded() -> None:
    """FMAbabld sets the headings of a book whose body is FM-Abhaya.

    It is almost certainly FM-Abhaya Bold. "Almost certainly" is not the
    standard for applying a mapping table, so the suspicion is recorded and the
    verdict is not changed.
    """
    font = identify_legacy_font("RFWEJF+FMAbabldBold")
    assert font.variant_of == "fmabhaya"
    assert font.convertible is False


def test_times_new_roman_survives_suffix_stripping() -> None:
    """ "Roman" is a real PostScript style suffix and also half this font's name."""
    assert normalise_font_name("ABCDEF+TimesNewRomanPSMT") == "timesnewroman"


# --------------------------------------------------------------------------
# Judging a font by all of its text, rather than one line of it
# --------------------------------------------------------------------------

#: Real lines from the textbook, set in a font named only "KQAHVM+CIDFont+F2".
#: Nothing in that name identifies anything, and the per-line non-ASCII rate is
#: below any usable threshold. 3,293 characters of it were being narrated.
UNNAMED_LEGACY = [
    ".re wOHdmk wud;H;=udf.a m‚jqvh",
    "f.ù .sh oYl follg wdikak ld,h f,dal b;sydih ;=< iqúfYaIS jQ ;dlaI‚l",
    "jkialï /ila isÿjQ ld,hls' f;dr;=re ;dlaIKh\" ikaksfõokh m%uqL lr.;a fiiq",
    "rgg jf. u uq¿ f,djg u fjkak keK myka",
]

#: The English translation printed on the same page, in Times New Roman.
REAL_ENGLISH = [
    "From the government, I received this as a gift",
    "I'll read it, light up my knowledge and practise thrift",
    "On my country's own behalf, I'll protect the national resources",
    "And offer this book to another one as a fresh garland of roses",
]


def test_an_unnamed_legacy_font_is_caught_once_its_text_is_aggregated() -> None:
    """The signal a single line cannot carry."""
    assert font_encoding_looks_wrong(" ".join(UNNAMED_LEGACY * 3))


def test_real_english_in_the_same_book_is_not_caught() -> None:
    assert not font_encoding_looks_wrong(" ".join(REAL_ENGLISH * 3))


def test_a_font_with_too_little_text_is_not_judged() -> None:
    """Acronym-heavy English scores like legacy text until there is enough of it.

    "(ILO) (FAO) (UNESCO) (IMF)" is a real line from the same book's glossary.
    """
    assert not font_encoding_looks_wrong("(ILO) (FAO) (UNESCO) (IMF) (WHO)")


def test_sinhala_text_is_never_judged_wrong() -> None:
    assert not font_encoding_looks_wrong("පොත් කියවීම මගින් දැනුම වර්ධනය වේ. " * 10)


def test_interior_capitals_separate_the_two_clusters() -> None:
    """The measured basis for the threshold, kept as an executable record."""
    legacy = interior_capital_ratio(" ".join(UNNAMED_LEGACY))
    english = interior_capital_ratio(" ".join(REAL_ENGLISH))
    assert legacy >= SUSPICIOUS_INTERIOR_CAPITAL_RATIO
    assert english < SUSPICIOUS_INTERIOR_CAPITAL_RATIO
    assert legacy > english * 2


def test_non_ascii_alone_would_have_missed_the_whole_book() -> None:
    """FM-Abhaya's non-ASCII rate is 0.073, below the span threshold of 0.08.

    Recorded because it is the reason the interior-capital signal exists.
    """
    assert non_ascii_ratio(" ".join(UNNAMED_LEGACY)) < SUSPICIOUS_NON_ASCII_RATIO


# --------------------------------------------------------------------------
# Scripts this reader has no voice for
#
# A Sinhala voice handed another script produces confident noise, and the
# listener cannot tell. Which script it is does not matter, so nothing here
# names one: the reader serves Sinhala, and everything else is equally
# unspeakable.
# --------------------------------------------------------------------------

#: A real line from the same textbook's trilingual inscription page.
OTHER_SCRIPT = "Aµ]ß öÁ¸Qh÷Á ¡¼uøÚU Põ¨÷£ß £» ©õnÁ¸®"


def test_another_script_is_withheld_rather_than_narrated() -> None:
    assert is_unreadable_script(OTHER_SCRIPT)


@pytest.mark.parametrize(
    "text",
    [
        "පොත් කියවීම මගින් දැනුම වර්ධනය වේ.",
        "From the government, I received this as a gift",
        "poth kiyaviima magin dhaenuma vardhanaya vee.",
    ],
)
def test_sinhala_and_latin_are_left_alone(text: str) -> None:
    assert not is_unreadable_script(text)


def test_legacy_sinhala_is_not_mistaken_for_another_script() -> None:
    """It decodes to Latin, so the script test must not be what catches it.

    Getting this wrong would route every legacy Sinhala page down the "we have
    no voice for this" path and lose the fact that a conversion table exists.
    """
    assert not is_unreadable_script("fmdñl mßiaÑ;h yd tu ldrKh ù we;")
    assert not is_unreadable_script(" ".join(UNNAMED_LEGACY))
