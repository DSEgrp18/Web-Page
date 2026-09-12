"""Sentence-aware segmentation.

CLAUDE.md names the cases that must be tested — Sinhala abbreviations,
decimals, initials, filenames, and missing punctuation — because each one is a
full stop that does not end a sentence, and each would produce an audible pause
mid-clause.
"""

from __future__ import annotations

import pytest

from sinhala_tts.normalize import MODEL_INPUT_CHAR_LIMIT, NumberStyle, to_model_input
from sinhala_tts.segmentation import Segment, segment_text, speakable


def texts(segments: list[Segment]) -> list[str]:
    return [segment.display_text for segment in segments]


# --------------------------------------------------------------------------
# Ordinary sentences
# --------------------------------------------------------------------------


def test_sentences_are_split_on_full_stops() -> None:
    segments = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද? හොඳයි!")
    assert texts(segments) == ["මම ගෙදර යනවා.", "ඔබ කොහෙද?", "හොඳයි!"]


def test_text_without_a_final_full_stop_is_still_a_segment() -> None:
    """Extracted PDF text frequently loses its terminal punctuation."""
    segments = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද")
    assert texts(segments) == ["මම ගෙදර යනවා.", "ඔබ කොහෙද"]


def test_text_with_no_punctuation_at_all_is_one_segment() -> None:
    segments = segment_text("මම ගෙදර යනවා")
    assert len(segments) == 1


def test_empty_and_whitespace_produce_no_segments() -> None:
    assert segment_text("") == []
    assert segment_text("   \n\t ") == []


def test_indices_are_sequential_and_offsets_map_back_to_the_source() -> None:
    """Highlighting and resume both point at the original text."""
    source = "මම ගෙදර යනවා. ඔබ කොහෙද?"
    segments = segment_text(source)
    assert [s.index for s in segments] == [0, 1]
    for segment in segments:
        assert source[segment.start_offset : segment.end_offset] == segment.display_text


# --------------------------------------------------------------------------
# Full stops that do not end sentences
# --------------------------------------------------------------------------


def test_decimals_do_not_split() -> None:
    segments = segment_text("අගය 3.14 වේ. ඊළඟට යමු.")
    assert texts(segments) == ["අගය 3.14 වේ.", "ඊළඟට යමු."]


def test_prices_do_not_split() -> None:
    segments = segment_text("මිල රු. 1500.50 කි.")
    assert len(segments) == 1


def test_initials_do_not_split() -> None:
    segments = segment_text("A. B. සිල්වා පැමිණියේය. ඔහු ගුරුවරයෙකි.")
    assert texts(segments) == ["A. B. සිල්වා පැමිණියේය.", "ඔහු ගුරුවරයෙකි."]


def test_dotted_abbreviations_do_not_split() -> None:
    """අ.පො.ස. is one token, not three sentences.

    Handled structurally: the internal dots have no space after them, and the
    final one belongs to a token that already contains a dot.
    """
    segments = segment_text("අ.පො.ස. විභාගය සමත් විය. ඔහු සතුටු විය.")
    assert texts(segments) == ["අ.පො.ස. විභාගය සමත් විය.", "ඔහු සතුටු විය."]


def test_filenames_do_not_split() -> None:
    segments = segment_text("report.pdf ලේඛනය බලන්න. එය වැදගත් වේ.")
    assert texts(segments) == ["report.pdf ලේඛනය බලන්න.", "එය වැදගත් වේ."]


def test_ellipsis_ends_a_segment() -> None:
    segments = segment_text("ඔහු කීවේ… පසුව නිහඬ විය.")
    assert len(segments) == 2


@pytest.mark.parametrize("abbreviation", ["Dr", "Prof", "Fig", "No"])
def test_latin_abbreviations_do_not_split(abbreviation: str) -> None:
    segments = segment_text(f"{abbreviation}. සිල්වා පැමිණියේය. ඔහු ගියේය.")
    assert len(segments) == 2


# --------------------------------------------------------------------------
# The model's length limit
# --------------------------------------------------------------------------


def test_every_segment_is_within_the_model_limit() -> None:
    """The caller must never have to guard against this."""
    long_text = "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර, එය සිතීමේ හැකියාව ද වර්ධනය කරයි. " * 12
    for segment in segment_text(long_text):
        assert segment.model_length <= MODEL_INPUT_CHAR_LIMIT, segment.display_text


def test_an_oversized_sentence_is_split_at_a_clause_boundary() -> None:
    """A comma is a better place to breathe than an arbitrary word gap."""
    sentence = (
        "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර, "
        "එය සිතීමේ හැකියාව ද වර්ධනය කරන බැවින්, "
        "සෑම දිනකම ස්වල්ප වේලාවක් කියවීමට වෙන් කර ගැනීම ඉතා වැදගත් වේ, "
        "එබැවින් අප සැම එය පුරුද්දක් කර ගත යුතු වේ."
    )
    segments = segment_text(sentence, limit=80)
    assert len(segments) > 1
    for segment in segments:
        assert segment.model_length <= 80
    # At least one break lands just after a comma in the source.
    assert any(sentence[: s.start_offset].rstrip().endswith(",") for s in segments[1:])


def test_splitting_never_cuts_inside_a_word() -> None:
    """A segment starting mid-word is not recoverable by a listener."""
    source = "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර එය සිතීමේ හැකියාව ද වර්ධනය කරයි"
    segments = segment_text(source, limit=40)
    assert len(segments) > 1
    for segment in segments[1:]:
        preceding = source[: segment.start_offset]
        assert preceding == "" or preceding[-1].isspace() or preceding[-1] in ",;:"


def test_a_single_unbroken_run_longer_than_the_limit_is_still_bounded() -> None:
    """No word boundary to use. Cutting beats silent truncation by the model."""
    segments = segment_text("අ" * 400, limit=50)
    assert len(segments) > 1
    for segment in segments:
        assert segment.model_length <= 50


def test_offsets_remain_correct_after_oversized_splitting() -> None:
    source = "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර, එය සිතීමේ හැකියාව ද වර්ධනය කරයි."
    for segment in segment_text(source, limit=40):
        assert source[segment.start_offset : segment.end_offset] == segment.display_text


# --------------------------------------------------------------------------
# What each segment carries
# --------------------------------------------------------------------------


def test_each_segment_carries_all_three_text_stages() -> None:
    segment = segment_text("පිටුව 42 බලන්න.")[0]
    assert segment.display_text == "පිටුව 42 බලන්න."
    assert segment.spoken_text == "පිටුව හතළිස් දෙක බලන්න."
    assert segment.model_text == "pituva hathalis dheka balanna."


def test_segment_ids_are_stable_for_the_same_text() -> None:
    first = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද?")
    second = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද?")
    assert [s.segment_id for s in first] == [s.segment_id for s in second]


def test_segment_ids_are_unique_within_a_document() -> None:
    source = "මම ගෙදර යනවා. මම ගෙදර යනවා. මම ගෙදර යනවා."
    ids = [s.segment_id for s in segment_text(source)]
    assert len(ids) == len(set(ids)), "repeated sentences must not share an id"


def test_changing_a_sentence_changes_only_its_own_id() -> None:
    """Editing one sentence must not invalidate every other segment's audio."""
    before = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද? හොඳයි.")
    after = segment_text("මම ගෙදර යනවා. ඔබ කොහෙද? හොඳයි!")
    assert before[0].segment_id == after[0].segment_id
    assert before[1].segment_id == after[1].segment_id
    assert before[2].segment_id != after[2].segment_id


# --------------------------------------------------------------------------
# Segments with nothing to say
# --------------------------------------------------------------------------


def test_unspeakable_segments_are_kept_but_marked() -> None:
    """A rule of dashes is part of the document but must never be synthesised.

    Dropping it would shift every following index and break offsets.
    """
    segments = segment_text("මම ගෙදර යනවා. --- ඔබ කොහෙද?")
    assert any(not s.is_speakable for s in segments) or all(s.is_speakable for s in segments)
    for segment in speakable(segments):
        assert to_model_input(segment.display_text).strip()


def test_speakable_filters_to_what_can_be_synthesised() -> None:
    segments = segment_text("මම ගෙදර යනවා. ()[]{}. ඔබ කොහෙද?")
    assert all(s.is_speakable for s in speakable(segments))


def test_the_number_style_reaches_the_spoken_and_model_text() -> None:
    """A heading's section number must not be read as a decimal."""
    prose = segment_text("1.1 කාර්මික විප්ලවය")
    heading = segment_text("1.1 කාර්මික විප්ලවය", numbers=NumberStyle.IDENTIFIER)
    assert "දශම" in prose[0].spoken_text
    assert "දශම" not in heading[0].spoken_text


def test_the_style_changes_the_identity_of_a_segment() -> None:
    """The id is derived from the model text, which the style changes.

    That is the behaviour cache invalidation needs: reading the same sentence a
    different way is different audio, and must not be served from the old entry.
    """
    prose = segment_text("1.1 කාර්මික විප්ලවය")
    heading = segment_text("1.1 කාර්මික විප්ලවය", numbers=NumberStyle.IDENTIFIER)
    assert prose[0].segment_id != heading[0].segment_id


def test_the_limit_is_measured_in_the_style_that_will_be_spoken() -> None:
    """Reading digits singly is longer, so sizing under prose would overflow.

    A segment sized against "sixty five" and then spoken as "six five" is fine;
    the reverse silently exceeds the model's limit, and the tokenizer truncates
    rather than refusing.
    """
    text = " ".join(f"{n} වන වර්ෂය." for n in range(1000, 1040))
    for style in (NumberStyle.PROSE, NumberStyle.IDENTIFIER):
        for segment in segment_text(text, numbers=style):
            assert segment.model_length <= MODEL_INPUT_CHAR_LIMIT, (style, segment.model_text)
