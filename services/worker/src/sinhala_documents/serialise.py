"""A prepared document, to JSON and back.

Extraction is expensive — about 30 seconds for a 168-page textbook — and until
now its result lived only in a dictionary inside the API process. That was fine
while everything else was in memory too. It stopped being fine the moment
documents became durable: the row said the book was ready, the job said
``succeeded``, and opening a page answered *"This document is not ready yet
(succeeded)"*, because the pages had died with the process.

It also blocks moving preparation onto a queue at all. A worker in another
process cannot put anything into the API's dictionary.

So the prepared document is written down. JSON rather than pickle, deliberately:
this is data the application trusts and reloads, and pickle turns a database row
into code execution. JSON also stays readable, which matters when somebody has
to work out why a book came back wrong.

**Round-tripping is exact**, and there is a test that says so on real extracted
pages. A serialiser that quietly drops a field would lose bounding boxes — and
with them the sentence highlighting a low-vision reader follows — while every
count and status still looked right.
"""

from __future__ import annotations

import json
from typing import Any

from .model import BoundingBox, PageKind, QualityState
from .pipeline import ReadableDocument, ReadablePage, ReadableSegment

#: Bumped when this format changes in a way old rows cannot be read in.
#: :func:`from_json` refuses a version it does not know rather than guessing,
#: because a half-understood page is worse than an absent one: the reader is
#: told the book is ready and then hears the wrong thing.
FORMAT_VERSION = 1


def to_json(document: ReadableDocument) -> str:
    return json.dumps(_document(document), ensure_ascii=False, separators=(",", ":"))


def from_json(raw: str | bytes) -> ReadableDocument:
    payload = json.loads(raw)
    # A stored payload that is not an object at all - a list, a bare number, a
    # truncated write - must raise the same way an unknown format does. Reaching
    # for .get() on it raises AttributeError instead, which is not a ValueError,
    # so it escapes every caller's except clause and turns a page request into a
    # 500 rather than an honest "not ready".
    if not isinstance(payload, dict):
        raise UnreadableFormat("A prepared document must be a JSON object.")

    version = payload.get("format")
    if version != FORMAT_VERSION:
        raise UnreadableFormat(
            f"Prepared documents in format {version!r} cannot be read by this build "
            f"(it understands {FORMAT_VERSION}). Re-prepare the document."
        )
    return ReadableDocument(
        version=payload["version"],
        pages=tuple(_read_page(page) for page in payload["pages"]),
        notes=tuple(payload["notes"]),
    )


class UnreadableFormat(ValueError):
    """The stored format is not one this build understands."""


def _document(document: ReadableDocument) -> dict[str, Any]:
    return {
        "format": FORMAT_VERSION,
        "version": document.version,
        "notes": list(document.notes),
        "pages": [_page(page) for page in document.pages],
    }


def _page(page: ReadablePage) -> dict[str, Any]:
    return {
        "page_index": page.page_index,
        "page_label": page.page_label,
        # StrEnum members are written as their values, so a row stays readable
        # and a renamed Python member does not silently change stored data.
        "kind": str(page.kind),
        "quality": str(page.quality),
        "notes": list(page.notes),
        "segments": [_segment(segment) for segment in page.segments],
    }


def _segment(segment: ReadableSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "index": segment.index,
        "page_index": segment.page_index,
        "page_label": segment.page_label,
        "display_text": segment.display_text,
        "spoken_text": segment.spoken_text,
        # Kept rather than recomputed. It is what the model was given, and
        # regenerating it later under a changed romaniser would silently
        # describe audio that was made from something else.
        "model_text": segment.model_text,
        "boxes": [_box(box) for box in segment.boxes],
    }


def _box(box: BoundingBox) -> list[float]:
    """A list, not an object. Four numbers repeated per line across a whole book
    is the bulk of this payload, and names on every one of them triple it."""
    return [box.x0, box.top, box.x1, box.bottom]


def _read_page(payload: dict[str, Any]) -> ReadablePage:
    return ReadablePage(
        page_index=payload["page_index"],
        page_label=payload["page_label"],
        kind=PageKind(payload["kind"]),
        quality=QualityState(payload["quality"]),
        segments=tuple(_read_segment(segment) for segment in payload["segments"]),
        notes=tuple(payload["notes"]),
    )


def _read_segment(payload: dict[str, Any]) -> ReadableSegment:
    return ReadableSegment(
        segment_id=payload["segment_id"],
        index=payload["index"],
        page_index=payload["page_index"],
        page_label=payload["page_label"],
        display_text=payload["display_text"],
        spoken_text=payload["spoken_text"],
        model_text=payload["model_text"],
        boxes=tuple(_read_box(box) for box in payload["boxes"]),
    )


def _read_box(values: list[float]) -> BoundingBox:
    x0, top, x1, bottom = values
    return BoundingBox(x0=x0, top=top, x1=x1, bottom=bottom)
