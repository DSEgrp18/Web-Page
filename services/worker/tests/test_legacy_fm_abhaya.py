"""FM-Abhaya to Sinhala Unicode conversion.

The failure this guards against is unusual and worth stating plainly: a wrong
mapping does not crash, and it does not produce garbage. It produces fluent,
grammatical Sinhala that says something the author never wrote, and no check
downstream can detect it. A listener who cannot see the page has no recourse at
all.

So the six supplied conversion examples are asserted character-for-character,
CLAUDE.md requires exactly that, and no entry here is invented.
"""

from __future__ import annotations

import unicodedata

import pytest

from sinhala_documents.legacy_fm_abhaya import (
    MAX_UNMAPPED_RATIO,
    ConversionReport,
    MappingUnavailable,
    convert,
    convert_with_report,
    count_invalid_sequences,
    data_dir,
    load_cases,
    load_mapping,
    repair_stranded_marks,
)

# --------------------------------------------------------------------------
# The supplied examples
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("legacy", "expected"), load_cases(), ids=lambda value: f"{len(value)}chars"
)
def test_every_supplied_case_converts_character_for_character(legacy: str, expected: str) -> None:
    """Not "mostly", not "looks right". Exactly."""
    assert convert(legacy) == expected


def test_all_six_supplied_cases_are_present() -> None:
    """A silently empty case file would make the test above pass vacuously."""
    assert len(load_cases()) == 6


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------


def test_the_vendored_table_loads() -> None:
    mapping = load_mapping()
    assert len(mapping.letters) > 1000
    assert mapping.rules


def test_bracket_keyed_entries_are_not_mistaken_for_section_headers() -> None:
    """Several letter keys begin with "[", as in ``[DD``.

    Treating any line starting with a bracket as a section header would drop
    them silently and leave brackets scattered through the output.
    """
    mapping = load_mapping()
    bracketed = [key for key in mapping.letters if key.startswith("[")]
    assert bracketed
    assert "[rules]" not in mapping.letters
    assert "[letters]" not in mapping.letters


def test_longer_keys_are_tried_before_the_letters_they_contain() -> None:
    """``fod`` is ``දො``; ``fo`` is ``දෙ`` and ``d`` is ``ා``.

    Matching shortest-first would turn one syllable into two.
    """
    assert convert("fod") == "දො"
    assert convert("fo") == "දෙ"


def test_a_missing_table_is_an_error_rather_than_an_empty_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Converting with no table returns the legacy bytes unchanged.

    Downstream that reads as "this text is fine", which is exactly backwards,
    so it has to fail instead.
    """
    from sinhala_documents import legacy_fm_abhaya

    monkeypatch.setenv(legacy_fm_abhaya.DATA_DIR_ENV, str(tmp_path))
    legacy_fm_abhaya.load_mapping.cache_clear()
    try:
        with pytest.raises(MappingUnavailable):
            legacy_fm_abhaya.load_mapping()
    finally:
        monkeypatch.delenv(legacy_fm_abhaya.DATA_DIR_ENV, raising=False)
        legacy_fm_abhaya.load_mapping.cache_clear()


def test_the_table_is_found_without_a_working_directory_assumption() -> None:
    assert (data_dir() / "fm_abhaya.tsv").is_file()


# --------------------------------------------------------------------------
# Vowel signs stranded in front of their consonant
# --------------------------------------------------------------------------

#: Real text from a Grade 11 history textbook. ``Þ`` is a variant code point for
#: the same glyph ``od`` spells, and the table has ``fod`` → ``දො`` but no
#: ``fÞ``, so the vowel sign is converted separately and left in front.
STRANDED = "f.a fÞr j;="


def test_a_stranded_vowel_sign_is_moved_after_its_consonant() -> None:
    assert convert(STRANDED) == "ගේ දොර වතු"


def test_the_repair_is_counted_rather_than_hidden() -> None:
    """A high count means the table had gaps for this text."""
    assert convert_with_report(STRANDED).repaired_marks == 1


def test_correctly_ordered_text_is_never_disturbed() -> None:
    """The dangerous case.

    In ``දෙර`` the vowel sign already follows its consonant and is followed by
    another one. A rule that moved every sign sitting before a consonant would
    turn this into ``දරෙ``.
    """
    text = "දෙර"
    assert repair_stranded_marks(text) == (text, 0)


def test_the_supplied_cases_still_pass_with_the_repair_in_place() -> None:
    """The repair goes beyond the table's documented two passes.

    Its licence to exist is that it changes nothing the table already gets
    right.
    """
    for legacy, expected in load_cases():
        assert convert(legacy) == expected


def test_output_is_normalised() -> None:
    """``ො`` is canonically ``ෙ`` followed by ``ා``; NFC joins them."""
    converted = convert(STRANDED)
    assert unicodedata.normalize("NFC", converted) == converted


# --------------------------------------------------------------------------
# Knowing when a conversion went wrong
# --------------------------------------------------------------------------


def test_a_clean_conversion_is_well_formed() -> None:
    report = convert_with_report("fmdñl mßiaÑ;h yd tu ldrKh ù we;")
    assert report.is_well_formed
    assert report.invalid_sequences == 0
    assert report.sinhala_characters > 0


@pytest.mark.parametrize(
    "english",
    [
        "This chapter examines the political and economic history of the island.",
        "Department of Education Publications, Government of Sri Lanka, 2018 edition.",
        "See Figure 3.2 and Table 4.1 for the comparative data on trade routes.",
        "Hemilia Vestatrix",
    ],
)
def test_english_put_through_the_table_is_not_well_formed(english: str) -> None:
    """CLAUDE.md asks for English and mixed-language negative examples.

    Note what this does *not* establish — see the test below.
    """
    assert not convert_with_report(english).is_well_formed


def test_well_formed_does_not_mean_the_input_was_fm_abhaya() -> None:
    """The limit of these checks, recorded so nobody relies on them further.

    Ordinary English sometimes converts to orthographically legal Sinhala. The
    font name is the gate; well-formedness only describes how a conversion of
    known-FM-Abhaya text went. CLAUDE.md says orthography checks cannot
    establish transcription accuracy, and this is what that means in practice.
    """
    report = convert_with_report(
        "The quick brown fox jumps over the lazy dog near the river bank today."
    )
    assert report.is_well_formed


def test_numbers_and_punctuation_convert_without_producing_sinhala() -> None:
    """A date is a valid conversion with no Sinhala letters in it.

    Requiring some Sinhala in every span would reject 371 perfectly good spans
    in the one real book this was measured on.
    """
    report = convert_with_report("2018'05'07")
    assert report.text == "2018.05.07"
    assert report.is_well_formed
    assert report.sinhala_characters == 0


def test_a_stranded_mark_with_nothing_to_attach_to_is_invalid() -> None:
    assert count_invalid_sequences("ේ") == 1
    assert count_invalid_sequences("කේ") == 0


def test_unmapped_latin_is_measured_against_the_output() -> None:
    report = ConversionReport(
        text="abcdefghij" + "ක" * 90,
        unmapped_characters=10,
        invalid_sequences=0,
        repaired_marks=0,
        sinhala_characters=90,
        total_characters=100,
    )
    assert report.unmapped_ratio == pytest.approx(0.10)
    assert report.unmapped_ratio <= MAX_UNMAPPED_RATIO
