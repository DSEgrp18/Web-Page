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

from .chapters import CHAPTERS_VERSION, Chapter
from .model import BoundingBox, PageKind, QualityState
from .pipeline import ReadableDocument, ReadablePage, ReadableSegment
from .structure import BlockRole

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
        # Absent in rows written before chapters were detected. Read as "not
        # known" rather than as an empty list, which would claim the book has
        # none. Adding the key is backward compatible, so the format is unchanged.
        chapters=_read_chapters(payload.get("chapters")),
    )


class UnreadableFormat(ValueError):
    """The stored format is not one this build understands."""


def _document(document: ReadableDocument) -> dict[str, Any]:
    return {
        "format": FORMAT_VERSION,
        "version": document.version,
        "notes": list(document.notes),
        "pages": [_page(page) for page in document.pages],
        "chapters": (
            None
            if document.chapters is None
            else {
                # Provenance only: which rule found them, for whoever has to work
                # out why a book's chapter list is wrong.
                "version": CHAPTERS_VERSION,
                "items": [_chapter(chapter) for chapter in document.chapters],
            }
        ),
    }


def _chapter(chapter: Chapter) -> dict[str, Any]:
    return {"title": chapter.title, "page_index": chapter.page_index, "number": chapter.number}


def _read_chapters(payload: dict[str, Any] | None) -> tuple[Chapter, ...] | None:
    if payload is None:
        return None
    return tuple(
        Chapter(title=item["title"], page_index=item["page_index"], number=item["number"])
        for item in payload["items"]
    )


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
    payload = {
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
    # Written only when structure found something. These were once not stored
    # at all, so under Celery - the worker prepares, the API reads back - every
    # heading returned as "unknown": passages lost their sections and a running
    # head was cited as evidence. The defaults are left out because most books
    # are prepared without a provider and have none to store; an absent key reads
    # back as exactly those defaults, which is also what older rows always were.
    # Adding optional keys is backward compatible, so the format is unchanged.
    if segment.role is not BlockRole.UNKNOWN:
        payload["role"] = str(segment.role)
    if segment.level is not None:
        payload["level"] = segment.level
    return payload


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
        role=BlockRole(payload.get("role", BlockRole.UNKNOWN)),
        level=payload.get("level"),
    )


def _read_box(values: list[float]) -> BoundingBox:
    x0, top, x1, bottom = values
    return BoundingBox(x0=x0, top=top, x1=x1, bottom=bottom)
