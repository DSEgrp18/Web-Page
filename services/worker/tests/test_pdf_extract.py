"""Extraction from digital PDFs, exercised against generated files.

Every PDF here is built in memory by :mod:`pdf_fixtures`. Nothing binary is
committed, which is what repository hygiene requires, and it means each test
states the exact document it is about rather than referring to a sample file
whose contents nobody can see in the diff.
"""

from __future__ import annotations

import pytest
from pdf_fixtures import (
    LEGACY_LINE,
    SINHALA_LINES,
    Page,
    Text,
    build_pdf,
    legacy_page,
    sinhala_page,
    two_column_page,
)

from sinhala_documents import (
    DocumentRejected,
    ExtractionMethod,
    PageKind,
    QualityState,
    extract_document,
)


def pages(*page_list: Page, labels=None):
    return extract_document(build_pdf(list(page_list), labels=labels)).pages


# --------------------------------------------------------------------------
# Ordinary Unicode Sinhala
# --------------------------------------------------------------------------


def test_sinhala_text_is_extracted_intact() -> None:
    page = pages(sinhala_page())[0]
    assert page.readable_text.splitlines() == list(SINHALA_LINES)
    assert page.kind is PageKind.TEXT
    assert page.quality is QualityState.ACCEPTED


def test_word_spacing_survives_extraction() -> None:
    """Words run together would reach the model as one unsplittable token.

    pdfplumber's word extractor discards the blank characters a PDF contains,
    and plenty of PDFs separate words by position with no space character at
    all. Losing the boundaries either way turns a sentence into one long word.
    """
    page = pages(sinhala_page())[0]
    assert " " in page.readable_text
    assert page.readable_text.count(" ") == sum(line.count(" ") for line in SINHALA_LINES)


def test_a_gap_with_no_space_character_still_becomes_a_word_break() -> None:
    """Two separately positioned words, with nothing between them in the file."""
    page = pages(Page(blocks=(Text("මම", x=72, y=700), Text("ගෙදර", x=140, y=700))))[0]
    assert page.readable_text == "මම ගෙදර"


def test_geometry_is_kept_for_every_line() -> None:
    """Highlighting, citations, and "read from here" all need a place on a page."""
    page = pages(sinhala_page())[0]
    first, second = page.lines[0], page.lines[1]
    assert first.box.x0 == pytest.approx(72.0, abs=1.0)
    # y is reported downwards from the top, whatever PDF's own origin does.
    assert first.box.top < second.box.top
    assert first.box.width > 0


def test_font_metadata_is_kept_for_every_span() -> None:
    span = pages(sinhala_page())[0].lines[0].spans[0]
    assert span.raw_font.endswith("NotoSerifSinhala")
    assert span.size == pytest.approx(12.0)
    assert span.method is ExtractionMethod.NATIVE


# --------------------------------------------------------------------------
# Legacy fonts
# --------------------------------------------------------------------------


def test_fm_abhaya_is_decoded_into_readable_sinhala() -> None:
    """The whole point of the mapping table: this text becomes speakable."""
    page = pages(legacy_page())[0]
    assert page.quality is QualityState.ACCEPTED
    assert page.readable_text == "පොමික පරිස්චිතය හා එම කාරණය වී ඇත"
    assert page.methods == frozenset({ExtractionMethod.LEGACY})


def test_the_original_characters_are_kept_after_decoding() -> None:
    """Once they are overwritten, a mistranslation cannot be diagnosed.

    This is the one place text a reader hears is not what the file contained,
    so the evidence has to survive.
    """
    span = pages(legacy_page())[0].lines[0].spans[0]
    assert span.original_text == LEGACY_LINE
    assert span.text != span.original_text


def test_untouched_text_carries_no_original() -> None:
    """Only a transformed span records one, so its presence means something."""
    span = pages(sinhala_page())[0].lines[0].spans[0]
    assert span.original_text == ""


def test_a_legacy_font_with_no_table_is_still_withheld() -> None:
    """Only FM-Abhaya has a validated mapping. The rest cannot be guessed at."""
    page = pages(legacy_page("DL-Manel"))[0]
    assert page.quality is QualityState.UNDECODABLE
    assert page.readable_text == ""


def test_a_withheld_line_stays_on_the_page_with_its_geometry() -> None:
    """Dropping it would make the page look blank instead of unreadable."""
    page = pages(legacy_page("DL-Manel"))[0]
    assert len(page.lines) == 1
    assert page.lines[0].box.width > 0
    assert page.notes


def test_the_note_distinguishes_decoded_from_undecodable() -> None:
    """Three different situations for whoever has to act on them."""
    decoded = pages(legacy_page("ABCDEF+FMAbhaya"))[0].lines[0].spans[0]
    unsupported = pages(legacy_page("DL-Manel"))[0].lines[0].spans[0]
    variant = pages(legacy_page("RFWEJF+FMAbabldBold"))[0].lines[0].spans[0]
    assert "Converted from" in decoded.notes[0]
    assert "no validated conversion table" in unsupported.notes[0]
    assert "has not been validated" in variant.notes[0]


def test_a_unicode_heading_survives_a_legacy_body() -> None:
    """Converted documents routinely mix the two, so the page is not the unit.

    Judging per page would either withhold the readable heading or narrate the
    unreadable body.
    """
    page = pages(
        Page(
            blocks=(
                Text("පළමු පරිච්ඡේදය", font="NotoSerifSinhala", size=18, y=720),
                Text(LEGACY_LINE, font="ABCDEF+FMAbhaya", y=690),
            )
        )
    )[0]
    assert page.readable_text.splitlines() == [
        "පළමු පරිච්ඡේදය",
        "පොමික පරිස්චිතය හා එම කාරණය වී ඇත",
    ]
    assert page.methods == {ExtractionMethod.NATIVE, ExtractionMethod.LEGACY}


# --------------------------------------------------------------------------
# Page classification
# --------------------------------------------------------------------------


def test_an_image_only_page_is_classified_for_ocr() -> None:
    page = pages(Page(images=1))[0]
    assert page.kind is PageKind.IMAGE
    assert page.image_count == 1
    assert "read aloud" in page.notes[0]


def test_an_image_only_page_is_never_reported_as_accepted() -> None:
    """It has no bad text because it has no text. It has still not been read."""
    assert pages(Page(images=1))[0].quality is QualityState.NEEDS_REVIEW


def test_a_page_with_both_text_and_images_keeps_its_text() -> None:
    page = pages(sinhala_page(images=2))[0]
    assert page.kind is PageKind.MIXED
    assert page.readable_text
    assert "not described" in " ".join(page.notes)


def test_a_blank_page_is_blank_rather_than_broken() -> None:
    page = pages(Page())[0]
    assert page.kind is PageKind.EMPTY
    assert page.quality is QualityState.ACCEPTED


def test_pages_are_classified_independently() -> None:
    """CLAUDE.md requires it, and real books mix typeset and scanned pages."""
    extracted = pages(sinhala_page(), Page(images=1), legacy_page("DL-Manel"))
    assert [page.kind for page in extracted] == [PageKind.TEXT, PageKind.IMAGE, PageKind.TEXT]


# --------------------------------------------------------------------------
# Reading order
# --------------------------------------------------------------------------


def test_a_two_column_page_declares_its_reading_order_uncertain() -> None:
    """Flattened extraction interleaves the columns line by line.

    The result is fluent-looking and wrong. It is not repaired here, but a
    reader who is told may skip the page; a reader who is not, cannot.
    """
    page = pages(two_column_page())[0]
    assert any("columns" in note for note in page.notes)


def test_a_single_column_page_makes_no_such_claim() -> None:
    """The margin to the right of a short paragraph is not a gutter."""
    page = pages(sinhala_page())[0]
    assert not any("columns" in note for note in page.notes)


# --------------------------------------------------------------------------
# Printed page numbers
# --------------------------------------------------------------------------


def test_printed_page_labels_are_reported_when_the_pdf_declares_them() -> None:
    """A citation to "page vi" has to mean what the reader would see printed."""
    extracted = pages(Page(), Page(), Page(), Page(), labels=[(0, "r"), (2, "D")])
    assert [page.page_label for page in extracted] == ["i", "ii", "1", "2"]


def test_file_position_is_always_available_even_without_labels() -> None:
    extracted = pages(Page(), Page())
    assert [page.page_index for page in extracted] == [0, 1]
    assert [page.page_label for page in extracted] == [None, None]


# --------------------------------------------------------------------------
# Selecting pages
# --------------------------------------------------------------------------


def test_only_the_requested_pages_are_extracted() -> None:
    """The first requested section has to be producible before the rest."""
    document = extract_document(
        build_pdf([sinhala_page(), legacy_page(), Page(images=1)]), page_indexes=[2, 0]
    )
    assert [page.page_index for page in document.pages] == [0, 2]


def test_a_stale_page_request_is_reported_rather_than_raised() -> None:
    document = extract_document(build_pdf([sinhala_page()]), page_indexes=[7])
    assert document.pages == ()
    assert any("requested pages" in note for note in document.notes)


# --------------------------------------------------------------------------
# Documents that cannot be processed
# --------------------------------------------------------------------------


def test_a_document_over_the_page_limit_is_refused_with_its_size() -> None:
    with pytest.raises(DocumentRejected) as error:
        extract_document(build_pdf([Page(), Page(), Page()]), max_pages=2)
    assert "3 pages" in str(error.value)


def test_a_file_that_is_not_a_pdf_is_refused() -> None:
    with pytest.raises(DocumentRejected):
        extract_document(b"this is not a pdf at all")


# --------------------------------------------------------------------------
# What the document as a whole reports
# --------------------------------------------------------------------------


def test_the_document_lists_what_still_needs_work() -> None:
    document = extract_document(
        build_pdf([sinhala_page(), Page(images=1), legacy_page("DL-Manel")])
    )
    assert [page.page_index for page in document.pages_needing_ocr] == [1]
    assert [page.page_index for page in document.pages_needing_review] == [1, 2]
    assert any("images with no readable text" in note for note in document.notes)


# --------------------------------------------------------------------------
# Content drawn outside the printed page
#
# Found in a real 168-page textbook: one page drew 3,322 of its 3,792
# characters off the sheet — an entire duplicated article, which extraction
# then interleaved character by character with the four visible lines.
# --------------------------------------------------------------------------


def test_text_drawn_outside_the_page_is_left_out() -> None:
    """It is invisible when the page is rendered, so it must not be narrated.

    A listener should get what a sighted reader gets, and this is not on the
    page at all.
    """
    page = pages(
        Page(
            blocks=(
                Text("මම ගෙදර යනවා", x=72, y=700),
                Text("කිසිවෙක් නොදකින පෙළ", x=900, y=700),
            )
        )
    )[0]
    assert page.readable_text == "මම ගෙදර යනවා"


def test_off_page_content_does_not_interleave_with_visible_text() -> None:
    """The failure mode: two runs at the same height merged into one line.

    Every word is present, the sentences are nonsense, and nothing about the
    output looks broken.
    """
    page = pages(
        Page(
            blocks=(
                Text("පළමු", x=72, y=700),
                Text("දෙවන", x=760, y=700),
                Text("තෙවන", x=72, y=680),
            )
        )
    )[0]
    assert [line.text for line in page.lines] == ["පළමු", "තෙවන"]


def test_dropping_off_page_content_is_reported() -> None:
    """A producer leaving this much on the pasteboard is worth knowing about."""
    page = pages(Page(blocks=(Text("හැංගුණු පෙළ " * 4, x=900, y=700),)))[0]
    assert any("outside the printed area" in note for note in page.notes)


def test_ordinary_pages_are_not_accused_of_hiding_anything() -> None:
    assert not any("outside the printed area" in note for note in pages(sinhala_page())[0].notes)


# --------------------------------------------------------------------------
# Fonts whose names identify nothing
#
# The real book set 3,293 characters in a font called only "CIDFont+F2".
# Nothing in the name to match, no Sinhala in the output, and a per-line
# non-ASCII rate below any usable threshold. All of it was being narrated.
# --------------------------------------------------------------------------

#: Legacy text long enough for the font to be judged on it, as it would be on
#: a real page.
UNNAMED_LEGACY_BODY = (
    "f.ù .sh oYl follg wdikak ld,h f,dal b;sydih ;=< iqúfYaIS jQ ;dlaI‚l "
    "jkialï /ila isÿjQ ld,hls' f;dr;=re ;dlaIKh ikaksfõokh m%uqL lr.;a fiiq "
    "lafIa;% /ilo fkdis;+ whqßka fjkia jQ nj wm oksuq' tu ksid wOHdmkh o "
)


def unnamed_legacy_page(*, with_known_legacy: bool = True) -> Page:
    blocks = [
        Text(UNNAMED_LEGACY_BODY, font="CIDFont+F2", y=700 - index * 16) for index in range(3)
    ]
    if with_known_legacy:
        blocks.append(Text(LEGACY_LINE, font="ABCDEF+FMAbhaya", y=620))
    return Page(blocks=tuple(blocks))


def test_a_font_that_identifies_nothing_is_judged_on_all_its_text() -> None:
    """One line carries too little signal. A page of it does not.

    The FM-Abhaya line on the same page decodes and stays readable, which is
    the point: the verdict is per font, not per page.
    """
    page = pages(unnamed_legacy_page())[0]
    assert page.quality is QualityState.UNDECODABLE
    assert UNNAMED_LEGACY_BODY not in page.readable_text
    assert page.readable_text == "පොමික පරිස්චිතය හා එම කාරණය වී ඇත"


def test_the_note_explains_what_the_font_was_judged_on() -> None:
    page = pages(unnamed_legacy_page())[0]
    notes = [note for span in page.lines[0].spans for note in span.notes]
    assert any("CIDFont+F2" in note for note in notes)


def test_it_is_withheld_even_with_no_legacy_font_beside_it() -> None:
    """An earlier version only flagged this case. A real book settled it.

    One page of the textbook was set entirely in a font called CIDFont+F2, with
    no identified legacy font on it to supply context — and flagged text is
    still narrated, so 3,242 characters of gibberish went to the reader.
    """
    page = pages(unnamed_legacy_page(with_known_legacy=False))[0]
    assert page.quality is QualityState.UNDECODABLE
    assert page.readable_text == ""


def test_the_note_only_claims_what_the_page_supports() -> None:
    """With a known legacy font beside it, this can be named as legacy text.

    Without one, all that is known is that it does not decode to anything
    readable — so that is all the note says.
    """
    with_context = pages(unnamed_legacy_page())[0]
    alone = pages(unnamed_legacy_page(with_known_legacy=False))[0]
    assert any("legacy" in n for span in with_context.lines[0].spans for n in span.notes)
    assert any(
        "neither Sinhala nor ordinary English" in n
        for span in alone.lines[0].spans
        for n in span.notes
    )


def test_readable_text_in_an_unknown_font_is_left_alone() -> None:
    """The same rule must not withhold ordinary English set in an odd font."""
    english = (
        "From the government, I received this as a gift. I will read it and light up my "
        "knowledge. On my country's own behalf, I will protect the national resources, and "
        "offer this book to another one as a fresh garland of roses in the coming year. "
    )
    page = pages(Page(blocks=(Text(english, font="CIDFont+F7", y=700),)))[0]
    assert page.quality is QualityState.ACCEPTED
    assert page.readable_text


def test_another_script_is_shown_but_not_read() -> None:
    """The book is trilingual; this reader has a Sinhala voice only."""
    page = pages(
        Page(blocks=(Text("Aµ]ß öÁ¸Qh÷Á ¡¼uøÚU Põ¨÷£ß £» ©õnÁ¸®", font="OtherScript", y=700),))
    )[0]
    assert page.readable_text == ""
    assert page.text != ""
