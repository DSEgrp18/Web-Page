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


def test_legacy_font_text_is_extracted_but_withheld() -> None:
    """The characters are real; their meaning is not. Narrating them is the bug."""
    page = pages(legacy_page())[0]
    assert page.text == LEGACY_LINE
    assert page.quality is QualityState.UNDECODABLE
    assert page.readable_text == ""
    assert page.methods == frozenset({ExtractionMethod.LEGACY})


def test_a_withheld_line_stays_on_the_page_with_its_geometry() -> None:
    """Dropping it would make the page look blank instead of unreadable."""
    page = pages(legacy_page())[0]
    assert len(page.lines) == 1
    assert page.lines[0].box.width > 0
    assert page.notes


def test_the_note_says_whether_a_conversion_table_exists() -> None:
    """Two different problems for whoever has to fix them."""
    convertible = pages(legacy_page("ABCDEF+FMAbhaya"))[0].lines[0].spans[0]
    unsupported = pages(legacy_page("DL-Manel"))[0].lines[0].spans[0]
    assert "converter is not implemented" in convertible.notes[0]
    assert "no validated conversion table" in unsupported.notes[0]


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
    assert page.readable_text == "පළමු පරිච්ඡේදය"
    assert page.quality is QualityState.UNDECODABLE
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
    extracted = pages(sinhala_page(), Page(images=1), legacy_page())
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
    document = extract_document(build_pdf([sinhala_page(), Page(images=1), legacy_page()]))
    assert [page.page_index for page in document.pages_needing_ocr] == [1]
    assert [page.page_index for page in document.pages_needing_review] == [1, 2]
    assert any("images with no readable text" in note for note in document.notes)
