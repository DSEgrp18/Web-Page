"""What the route modules share: ownership, readiness, and a few helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sinhala_documents import media_type_for

from ..preparation import get_prepared
from ..schemas import DocumentDetail
from ..storage import Document, Job, Store

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
