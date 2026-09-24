"""What the route modules share: ownership, readiness, and a few helpers."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sinhala_documents import media_type_for
from sinhala_documents.pipeline import ReadableDocument
from sinhala_documents.serialise import UnreadableFormat, from_json

from ..preparation import get_prepared
from ..schemas import DocumentDetail
from ..storage import Document, Job, Reading, Store

if TYPE_CHECKING:
    from ..app import Deps

#: Names the audio a placeholder in the one place a client cannot miss it.
REAL_MODEL_HEADER = "X-Reader-Real-Model"


def owned_in(deps: Deps, document_id: str, owner: str) -> Document:
    """The caller's own document, or 404: another reader's is absent, never forbidden."""
    document = deps.store.get_document(document_id, owner)
    if document is None:
        # Deliberately the same answer as "no such document".
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    return document


def readable_in(deps: Deps, document_id: str, reader: str) -> Reading:
    """The document as this reader may read it, or 404.

    Its owner reads it as it stands; an active member of a class it is
    published to reads the published version. Anyone else finds nothing,
    exactly as for a document that does not exist.
    """
    reading = deps.store.readable_document(document_id, reader)
    if reading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    return reading


#: What a class reader is told on a page their teacher withheld.
WITHHELD_NOTE = "Your teacher has withheld this page, so it is not read aloud."

#: Published versions, deserialised. Small, like the owner's cache.
_PINNED: dict[tuple[str, str], ReadableDocument] = {}
_PINNED_LOCK = threading.Lock()
MAX_PINNED = 8


def _pinned(deps: Deps, document_id: str, version: str) -> ReadableDocument | None:
    key = (document_id, version)
    with _PINNED_LOCK:
        cached = _PINNED.get(key)
    if cached is not None:
        return cached
    payload = deps.store.get_prepared_version(document_id, version)
    if payload is None:
        return None
    try:
        prepared = from_json(payload)
    except (UnreadableFormat, ValueError, KeyError):
        return None
    with _PINNED_LOCK:
        if len(_PINNED) >= MAX_PINNED:
            _PINNED.pop(next(iter(_PINNED)))
        _PINNED[key] = prepared
    return prepared


def prepared_for_in(
    deps: Deps, reading: Reading, *, required: bool = True
) -> ReadableDocument | None:
    """The pages this reader may read: 409 while not ready, unless not required.

    A class reader gets the published version with every withheld page emptied
    of its sentences, so it is absent from narration, from answers and from
    anything else built on the pages, and says why instead.
    """
    document = reading.document
    if reading.as_owner:
        prepared = get_prepared(deps.store, document.document_id)
        if prepared is not None and document.version is not None:
            return prepared
    elif document.version is not None:
        pinned = _pinned(deps, document.document_id, document.version)
        if pinned is not None:
            if not reading.withheld:
                return pinned
            return replace(
                pinned,
                pages=tuple(
                    replace(page, segments=(), notes=(WITHHELD_NOTE,))
                    if page.page_index in reading.withheld
                    else page
                    for page in pinned.pages
                ),
            )
    if not required:
        return None
    if reading.as_owner:
        # The owner can be told where preparation has got to; a class reader
        # has no business with the teacher's jobs.
        jobs = deps.store.jobs_for(document.document_id, document.owner)
        latest = jobs[-1] if jobs else None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This document is not ready yet ({latest.state if latest else 'unknown'}).",
        )
    raise HTTPException(status.HTTP_409_CONFLICT, "This document is not ready yet.")


def reading_detail(deps: Deps, reading: Reading, reader: str) -> DocumentDetail:
    """A book's detail as this reader sees it: the owner's full view, or a
    class reader's, with their own position and no preparation job."""
    if reading.as_owner:
        return _document_detail(deps.store, reading.document.document_id, reader)
    document = reading.document
    prepared = prepared_for_in(deps, reading, required=False)
    return DocumentDetail.of(
        document,
        None,
        progress=deps.store.get_progress(document.document_id, reader),
        chapters=prepared.chapters if prepared else None,
        media_type=media_type_for(document.filename, deps.store.get_source(document.document_id)),
    )


def prepared_or_409_in(deps: Deps, document: Document):
    """The document's prepared pages, or 409 while it is still being prepared."""
    prepared = get_prepared(deps.store, document.document_id)
    if prepared is None or document.version is None:
        jobs = deps.store.jobs_for(document.document_id, document.owner)
        latest = jobs[-1] if jobs else None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This document is not ready yet ({latest.state if latest else 'unknown'}).",
        )
    return prepared


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse one `Range: bytes=…` into inclusive offsets, or None for the lot.

    Deliberately narrow. Only a single range is honoured, because that is all
    pdf.js asks for and a multipart/byteranges response is a lot of machinery
    for a case that does not arise here. Anything unparseable, reversed, or
    past the end returns None, which serves the whole file — a correct answer
    to the request, just not a partial one. RFC 9110 permits ignoring a Range
    that cannot be satisfied, and serving 200 keeps a strange header from
    turning into a failed page rather than a slower one.
    """
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    spec = header[len("bytes=") :].strip()
    first, _, last = spec.partition("-")
    try:
        if not first:
            # `bytes=-500`: the final 500 bytes, which is how pdf.js finds the
            # cross-reference table.
            length = int(last)
            if length <= 0:
                return None
            return max(0, size - length), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start > end or start >= size:
        return None
    return start, min(end, size - 1)


def _document_detail(
    store: Store, document_id: str, owner: str, job: Job | None = None
) -> DocumentDetail:
    document = store.get_document(document_id, owner)
    assert document is not None
    jobs = store.jobs_for(document_id, owner)
    latest = job or (jobs[-1] if jobs else None)
    prepared = get_prepared(store, document_id) if document.version else None
    return DocumentDetail.of(
        document,
        latest,
        progress=store.get_progress(document_id, owner),
        chapters=prepared.chapters if prepared else None,
        media_type=media_type_for(document.filename, store.get_source(document_id)),
    )
