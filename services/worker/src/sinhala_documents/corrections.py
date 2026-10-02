"""Teacher corrections to OCR or extraction on one page.

A correction replaces what is read on that page, bumps the document version,
and invalidates audio built from the old text (CLAUDE.md).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from sinhala_tts.normalize import MODEL_INPUT_CHAR_LIMIT, to_speech_text
from sinhala_tts.segmentation import segment_text

from .model import PageKind, QualityState
from .pipeline import ReadableDocument, ReadablePage, ReadableSegment
from .structure import BlockRole


def _new_version(previous: str, page_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{page_index}:{text}".encode("utf-8")).hexdigest()[:12]
    return f"{previous}+page{page_index}-corr-{digest}"


def apply_page_correction(
    document: ReadableDocument, page_index: int, display_text: str
) -> ReadableDocument:
    """Return a new prepared document with one page replaced by reviewed text."""
    page = document.page(page_index)
    if page is None:
        raise ValueError(f"Page {page_index} is not in this document.")

    spoken_base = to_speech_text(display_text)
    segments: list[ReadableSegment] = []
    for piece in segment_text(spoken_base, limit=MODEL_INPUT_CHAR_LIMIT):
        if not piece.is_speakable:
            continue
        segment_id = f"{page_index:04d}-corr-{len(segments)}"
        segments.append(
            ReadableSegment(
                segment_id=segment_id,
                index=0,
                page_index=page_index,
                page_label=page.page_label,
                display_text=piece.display_text,
                spoken_text=piece.spoken_text,
                model_text=piece.model_text,
                boxes=(),
                role=BlockRole.PARAGRAPH,
            )
        )

    notes = tuple(n for n in page.notes if not n.startswith("note:ocr_recognised"))
    notes = notes + ("note:page_teacher_corrected",)

    new_page = replace(
        page,
        kind=PageKind.TEXT if segments else PageKind.EMPTY,
        quality=QualityState.ACCEPTED,
        segments=tuple(segments),
        notes=notes,
    )
    pages = tuple(new_page if p.page_index == page_index else p for p in document.pages)
    updated = replace(
        document,
        version=_new_version(document.version, page_index, display_text),
        pages=pages,
    )
    return _reindex_segments(updated)


def _reindex_segments(document: ReadableDocument) -> ReadableDocument:
    pages: list[ReadablePage] = []
    index = 0
    for page in document.pages:
        segments: list[ReadableSegment] = []
        for segment in page.segments:
            segments.append(replace(segment, index=index))
            index += 1
        pages.append(replace(page, segments=tuple(segments)))
    return replace(document, pages=tuple(pages))
