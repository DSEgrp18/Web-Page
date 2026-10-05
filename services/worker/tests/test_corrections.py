"""Teacher page corrections bump version and reindex segments."""

from __future__ import annotations

import pytest

from sinhala_documents.corrections import UnchangedCorrection, apply_page_correction
from sinhala_documents.model import PageKind, QualityState
from sinhala_documents.pipeline import ReadableDocument, ReadablePage, ReadableSegment
from sinhala_documents.structure import BlockRole


def _page(text: str) -> ReadableDocument:
    segment = ReadableSegment(
        segment_id="0000-s0",
        index=0,
        page_index=0,
        page_label="1",
        display_text=text,
        spoken_text=text,
        model_text=text,
        boxes=(),
        role=BlockRole.PARAGRAPH,
    )
    return ReadableDocument(
        version="book-v1",
        pages=(
            ReadablePage(
                page_index=0,
                page_label="1",
                kind=PageKind.TEXT,
                quality=QualityState.NEEDS_REVIEW,
                segments=(segment,),
                notes=("note:ocr_recognised",),
            ),
        ),
        notes=(),
    )


def test_correction_bumps_version_and_accepts_page() -> None:
    doc = _page("ocr text")
    before = doc.version
    updated = apply_page_correction(doc, 0, "සිසුන්ට නිවැරදි පෙළ.")
    assert updated.version != before
    assert updated.version.startswith(before)
    page = updated.page(0)
    assert page is not None
    assert page.quality is QualityState.ACCEPTED
    assert any(n.startswith("note:page_corrected") for n in page.notes)
    assert updated.segments[0].index == 0


def test_numbers_stay_digits_in_the_corrected_display_text() -> None:
    updated = apply_page_correction(_page("ocr text"), 0, "ලකුණු 2,5 ක් සහ 0 ක්.")
    shown = " ".join(segment.display_text for segment in updated.segments)
    assert "2,5" in shown and "0" in shown
    assert "බින්දුව" not in shown
    assert any("බින්දුව" in segment.spoken_text for segment in updated.segments)


def test_saving_the_unchanged_text_is_refused() -> None:
    doc = _page("ocr  text")
    with pytest.raises(UnchangedCorrection):
        apply_page_correction(doc, 0, "ocr text")
    assert doc.page(0).quality is QualityState.NEEDS_REVIEW
