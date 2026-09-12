"""The normaliser that runs before the vendored front end.

The companion file ``test_text_frontend_characterisation.py`` records what the
raw front end does, including three defects. This file asserts that the two
which cause data loss are fixed by the time text reaches the model, and that the
third is still present and still deliberately unfixed.
"""

from __future__ import annotations

import pytest

from sinhala_tts.normalize import (
    MODEL_INPUT_CHAR_LIMIT,
    NORMALIZER_VERSION,
    contains_sinhala,
    exceeds_model_limit,
    expand_numbers,
    is_speakable,
    normalize_whitespace,
    to_model_input,
    to_speech_text,
)
from sinhala_tts.vendor.sinhala_text import to_ascii

# --------------------------------------------------------------------------
# DEFECT 1 fixed: numbers survive to the model
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("display", "spoken"),
    [
        ("පිටුව 42 බලන්න", "පිටුව හතළිස් දෙක බලන්න"),
        ("2024 වර්ෂය", "දෙදහස් විසි හතර වර්ෂය"),
        ("අංක 7 සහ අංක 8", "අංක හත සහ අංක අට"),
    ],
)
def test_numbers_are_written_out_before_the_lossy_front_end(display: str, spoken: str) -> None:
    assert to_speech_text(display) == spoken


def test_the_page_number_now_reaches_the_model() -> None:
    """The regression that motivated this module.

    Raw, the front end narrates "පිටුව 42 බලන්න" as "pituva balanna" — the
    listener is told to look at a page and not told which.
    """
    assert to_ascii("පිටුව 42 බලන්න") == "pituva balanna"
    assert to_model_input("පිටුව 42 බලන්න") == "pituva hathalis dheka balanna"


def test_decimals_read_the_fraction_digit_by_digit() -> None:
    """3.14 is "three point one four", not "three point fourteen"."""
    assert to_speech_text("3.14") == "තුන දශම එක හතර"


def test_thousands_separators_are_understood() -> None:
    assert to_speech_text("1,500.50") == "එක්දහස් පන්සියය දශම පහ බින්දුව"


def test_percent_marker_precedes_the_number() -> None:
    """Sinhala reverses the written order: 50% is සියයට පනහ."""
    assert to_speech_text("50% සහ 25%") == "සියයට පනහ සහ සියයට විසි පහ"


def test_numbers_too_large_are_read_digit_by_digit_not_dropped() -> None:
    """Clumsy on purpose. Nothing is lost and nothing is invented."""
    assert to_speech_text("12345") == "එක දෙක තුන හතර පහ"


def test_no_digit_ever_reaches_the_front_end() -> None:
    """The invariant, stated as a property over the real defect cases.

    The front end deletes digits instead of refusing them, so a digit that
    survives normalisation is not a mispronunciation — it is silence where a
    number should be, which a listener cannot detect.
    """
    cases = [
        "2018.05.07",
        "1.1.1",
        "අංක 65C",
        "10.5.2018 දින",
        "3.14.15",
        "1,500.50.25",
    ]
    for case in cases:
        assert not any(c.isdigit() for c in to_speech_text(case)), case


def test_a_dotted_date_keeps_its_last_part() -> None:
    """2018.05.07 lost the 07 entirely.

    _NUMBER takes "2018.05" as a decimal and its lookbehind then refuses "07"
    because a dot precedes it, so the day reached the front end and vanished.
    The listener heard a date with a missing part and nothing to indicate it.
    """
    spoken = to_speech_text("2018.05.07")
    assert "හත" in spoken, spoken
    assert to_model_input("2018.05.07").endswith("hatha")


def test_a_trailing_identifier_digit_survives() -> None:
    """අංක 65C: the digits were expanded, and would be dropped if they were not."""
    assert not any(c.isdigit() for c in to_speech_text("අංක 65C"))


def test_expansion_does_not_glue_the_number_to_the_next_word() -> None:
    """A regex that consumed the trailing space would recreate defect 2 here."""
    spoken = to_speech_text("පිටුව 42 බලන්න")
    assert " බලන්න" in spoken
    assert "  " not in spoken


def test_numbers_can_be_left_alone() -> None:
    """With expansion off the digits are still deleted downstream, which is why
    it defaults to on. The switch exists for comparison during evaluation."""
    assert to_speech_text("පිටුව 42 බලන්න", numbers_as_words=False) == "පිටුව 42 බලන්න"
    assert to_model_input("පිටුව 42 බලන්න", numbers_as_words=False) == "pituva balanna"


# --------------------------------------------------------------------------
# DEFECT 2 fixed: line breaks no longer join words
# --------------------------------------------------------------------------


def test_newlines_become_spaces_instead_of_disappearing() -> None:
    assert to_ascii("මම\nගෙදර") == "mamagedhara"  # raw front end, unchanged
    assert to_model_input("මම\nගෙදර") == "mama gedhara"


def test_tabs_become_spaces() -> None:
    assert to_model_input("column\tvalue") == "cholumn value"


def test_runs_of_whitespace_collapse() -> None:
    assert normalize_whitespace("  spaced   \n\n  out  ") == "spaced out"


def test_zero_width_characters_are_removed_not_spaced() -> None:
    """A soft hyphen or zero-width space must not split a word in two.

    PDF layout inserts soft hyphens at line breaks, so turning one into a space
    would break the word it was meant to be invisible inside.
    """
    assert normalize_whitespace("සම්­පූර්ණ") == "සම්පූර්ණ"
    assert normalize_whitespace("වචන​යක්") == "වචනයක්"


def test_zero_width_joiner_is_preserved_for_the_front_end() -> None:
    """U+200D is meaningful in Sinhala conjuncts. The front end removes it at
    the right moment; this module must not remove it early."""
    assert "‍" in normalize_whitespace("ක්‍ෂ")
    assert to_model_input("ක්‍ෂ") == "ksha"


# --------------------------------------------------------------------------
# DEFECT 3 still present, on purpose
# --------------------------------------------------------------------------


def test_english_only_text_is_still_mangled() -> None:
    """Not fixed here, and the test says so.

    Routing English-only segments differently would change pronunciation on
    reasoning alone. That needs a listening comparison first, so the behaviour
    is left alone and recorded rather than quietly altered.
    """
    assert to_model_input("computer") == "chomputher"


def test_english_inside_sinhala_is_unaffected() -> None:
    assert to_model_input("මෙය PDF ලේඛනයකි") == "meya pdf leekanayaki"


def test_contains_sinhala_detects_the_dispatch_condition() -> None:
    assert contains_sinhala("මෙය PDF ලේඛනයකි")
    assert not contains_sinhala("computer")
    assert not contains_sinhala("2024")


# --------------------------------------------------------------------------
# Empty output must never reach the model
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "()[]{}#@", "\n\n\t"])
def test_text_that_normalises_to_nothing_is_not_speakable(text: str) -> None:
    """Synthesising an empty string yields a silent clip that a cache would
    store as valid audio, and a listener would experience as a skipped sentence
    with no explanation."""
    assert not is_speakable(to_model_input(text))


def test_real_text_is_speakable() -> None:
    assert is_speakable(to_model_input("මම ගෙදර යනවා."))
    assert is_speakable(to_model_input("42"))


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "පිටුව 42 බලන්න",
        "2024 වර්ෂය දෙදහස්",
        "1,500.50 සහ 50%",
        "මෙය PDF ලේඛනයකි",
        "line one\nline two",
        "ක්‍ෂ ඥ ඤ",
    ],
)
def test_model_input_is_always_ascii(text: str) -> None:
    """Any non-ASCII byte reaching the tokenizer becomes [UNK]."""
    assert to_model_input(text).isascii()


@pytest.mark.parametrize(
    "text",
    ["පිටුව 42 බලන්න", "  2024  වර්ෂය  ", "3.14 සහ 50%"],
)
def test_output_has_no_double_or_edge_spaces(text: str) -> None:
    for produced in (to_speech_text(text), to_model_input(text)):
        assert "  " not in produced
        assert produced == produced.strip()


def test_normalizer_version_is_declared() -> None:
    """Cache identity includes it, so it has to exist and be a plain string."""
    assert isinstance(NORMALIZER_VERSION, str)
    assert NORMALIZER_VERSION


def test_expand_numbers_leaves_text_without_digits_untouched() -> None:
    assert expand_numbers("මම ගෙදර යනවා.") == "මම ගෙදර යනවා."


def test_speech_text_stays_readable_sinhala() -> None:
    """The middle stage must remain Sinhala a person can check, not ASCII.

    Display and retrieval keep the original text; this is the separate spoken
    form CLAUDE.md requires, and it is only useful if a reviewer can read it.
    """
    spoken = to_speech_text("පිටුව 42 බලන්න")
    assert contains_sinhala(spoken)
    assert not spoken.isascii()


# --------------------------------------------------------------------------
# The model's own text-length limit
# --------------------------------------------------------------------------


def test_model_limit_matches_the_tokenizer_the_model_ships_with() -> None:
    """250 is VoiceBpeTokenizer.char_limits["en"], read from coqui-tts.

    Not a number we chose. If it ever disagrees with the installed library the
    segmenter is sized wrong, and segments would be silently truncated.
    """
    assert MODEL_INPUT_CHAR_LIMIT == 250


def test_ordinary_sentences_are_well_inside_the_limit() -> None:
    text = "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර, එය සිතීමේ හැකියාව ද වර්ධනය කරයි."
    assert not exceeds_model_limit(to_model_input(text))


def test_an_oversized_segment_is_detected() -> None:
    long_text = "මම ගෙදර යනවා. " * 40
    model_text = to_model_input(long_text)
    assert len(model_text) > MODEL_INPUT_CHAR_LIMIT
    assert exceeds_model_limit(model_text)


def test_the_limit_applies_to_model_input_not_display_text() -> None:
    """Romanisation changes length, so the two counts differ.

    Checking the Sinhala would measure the wrong string.
    """
    text = "ආයුබෝවන් " * 20
    assert len(to_model_input(text)) != len(text)
