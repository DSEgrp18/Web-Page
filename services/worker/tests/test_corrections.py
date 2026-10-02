"""Teacher page corrections bump version and reindex segments."""

from __future__ import annotations

from sinhala_documents.corrections import apply_page_correction
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
    assert any(n.startswith("note:page_teacher_corrected") for n in page.notes)
    assert updated.segments[0].index == 0
