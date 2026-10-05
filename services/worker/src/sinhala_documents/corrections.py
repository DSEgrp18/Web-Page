"""Hand corrections to OCR or extraction on one page.

A correction replaces what is read on that page, bumps the document version,
and invalidates audio built from the old text (CLAUDE.md).

The corrected text is the page's new *display* text. Numbers are written out
only in the spoken text, as everywhere else: an earlier version expanded the
whole correction first, so "2,5" was shown to the reader as "දෙක,පහ".
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from sinhala_tts.normalize import MODEL_INPUT_CHAR_LIMIT
from sinhala_tts.segmentation import segment_text

from .model import PageKind, QualityState
from .pipeline import ReadableDocument, ReadablePage, ReadableSegment
from .structure import BlockRole


class UnchangedCorrection(ValueError):
    """The submitted text is the page's current text.

    Saving it would mark unreviewed OCR as corrected and accepted: a claim
    about the text that nobody made.
    """


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


def _new_version(previous: str, page_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{page_index}:{text}".encode()).hexdigest()[:12]
    return f"{previous}+page{page_index}-corr-{digest}"


def apply_page_correction(
    document: ReadableDocument, page_index: int, display_text: str
) -> ReadableDocument:
    """Return a new prepared document with one page replaced by reviewed text."""
    page = document.page(page_index)
    if page is None:
        raise ValueError(f"Page {page_index} is not in this document.")

    current = " ".join(segment.display_text for segment in page.segments)
    if _same_text(current, display_text):
        raise UnchangedCorrection(f"Page {page_index} already reads this way.")

    segments: list[ReadableSegment] = []
    for piece in segment_text(display_text, limit=MODEL_INPUT_CHAR_LIMIT):
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
    # The route checks ownership, not who reviewed the text, so the note says
    # only what is known: a person replaced it.
    notes = notes + ("note:page_corrected",)

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
