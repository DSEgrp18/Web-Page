"""Publishing a book to a class: review, attest, share, and stop sharing.

A teacher prepares a book once for a whole class, in three steps:

1. **Review.** Every page flagged for checking (a scanned page read by OCR,
   say) gets a decision: accept it, or withhold it. A withheld page is never
   read to the class, searched, or quizzed, and its readers are told it was
   withheld.
2. **Attest.** The teacher states the basis on which they may share it. The
   service cannot check that, so it records who said so, on what basis, and
   when, and sharing stays limited to the teacher's own classes.
3. **Share.** The book is pinned at its current version and shared with the
   classes chosen. Publishing is refused, as ``unreviewed_pages``, until every
   flagged page has a decision.

Sharing stops per class, on the class's next request. Only the book's owner can
do any of this, and only a teacher can publish.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sinhala_documents import media_type_for
from sinhala_documents.model import QualityState
from sinhala_documents.serialise import to_json

from ..schemas import DocumentSummary
from ..security import require_owner, require_user
from ..storage import (
    AuditEvent,
    PageDecision,
    Publication,
    RightsBasis,
    Role,
    User,
    new_id,
)
from .common import owned_in, prepared_or_409_in

if TYPE_CHECKING:
    from ..app import Deps

CurrentUser = Depends(require_user)


class ReviewBody(BaseModel):
    decision: PageDecision


class PublishBody(BaseModel):
    class_ids: list[str] = Field(min_length=1, max_length=50)
    basis: RightsBasis
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _other_needs_a_note(self) -> PublishBody:
        if self.basis is RightsBasis.OTHER and not (self.note or "").strip():
            raise ValueError("Say what the basis is when it is 'other'.")
        return self


class FlaggedPage(BaseModel):
    page_index: int
    page_label: str | None
    quality: str = Field(description="Why it was flagged: needs_review.")
    notes: list[str]
    decision: str | None = Field(description="accepted, withheld, or null if undecided.")


class Review(BaseModel):
    """The pages of the current version a teacher must decide on before sharing."""

    version: str
    pages: list[FlaggedPage]
    undecided: int
    ready_to_publish: bool


class PublicationDetail(BaseModel):
    version: str
    basis: str
    note: str | None
    attested_at: str
    published_at: str
    class_ids: list[str]
    stale: bool = Field(
        description="True when the book has changed since it was shared; publish again to update."
    )


class ClassBook(BaseModel):
    """A book shared with one of this reader's classes."""

    class_id: str
    class_name: str
    book: DocumentSummary


def register(app: FastAPI, deps: Deps) -> None:
    """Add the publishing routes to ``app``, acting through ``deps``."""
    store = deps.store

    def owned_ready(document_id: str, owner: str):
        document = owned_in(deps, document_id, owner)
        return document, prepared_or_409_in(deps, document)

    def review_of(document_id: str, owner: str) -> Review:
        document, prepared = owned_ready(document_id, owner)
        assert document.version is not None
        decisions = store.page_reviews(document_id, owner, document.version)
        flagged = [
            FlaggedPage(
                page_index=page.page_index,
                page_label=page.page_label,
                quality=str(page.quality),
                notes=list(page.notes),
                decision=str(decisions[page.page_index]) if page.page_index in decisions else None,
            )
            for page in prepared.pages
            if page.quality is QualityState.NEEDS_REVIEW
        ]
        undecided = sum(1 for page in flagged if page.decision is None)
        return Review(
            version=document.version,
            pages=flagged,
            undecided=undecided,
            ready_to_publish=undecided == 0,
        )

    @app.get("/documents/{document_id}/review", tags=["publishing"])
    def get_review(document_id: str, owner: str = Depends(require_owner)) -> Review:
        """The pages flagged for checking, and what has been decided about each."""
        return review_of(document_id, owner)

    @app.put("/documents/{document_id}/review/{page_index}", tags=["publishing"])
    def decide_page(
        document_id: str, page_index: int, body: ReviewBody, owner: str = Depends(require_owner)
    ) -> Review:
        """Accept or withhold one flagged page, for the book as it is now."""
        document, prepared = owned_ready(document_id, owner)
        page = prepared.page(page_index)
        if page is None or page.quality is not QualityState.NEEDS_REVIEW:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such flagged page.")
        assert document.version is not None
        store.put_page_review(document_id, owner, document.version, page_index, body.decision)
        return review_of(document_id, owner)

    @app.get("/documents/{document_id}/publication", tags=["publishing"])
    def get_publication(
        document_id: str, owner: str = Depends(require_owner)
    ) -> PublicationDetail | None:
        """Where the book is shared, on what basis, and whether it has changed since."""
        document = owned_in(deps, document_id, owner)
        found = store.publication(document_id, owner)
        if found is None:
            return None
        publication, class_ids = found
        return PublicationDetail(
            version=publication.version,
            basis=str(publication.basis),
            note=publication.note,
            attested_at=publication.attested_at,
            published_at=publication.published_at,
            class_ids=class_ids,
            stale=publication.version != document.version,
        )

    @app.post("/documents/{document_id}/publish", tags=["publishing"])
    def publish(
        document_id: str, body: PublishBody, user: User = CurrentUser
    ) -> PublicationDetail | None:
        """Share the book, at its current version, with some of the teacher's classes.

        Refused with 409 ``unreviewed_pages`` while any flagged page is undecided.
        Publishing again moves the pin to the book as it is now.
        """
        document, prepared = owned_ready(document_id, user.user_id)
        if user.role is not Role.TEACHER:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a teacher can share a book.")
        if not review_of(document_id, user.user_id).ready_to_publish:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "unreviewed_pages", "message": "Decide on every flagged page first."},
            )
        assert document.version is not None
        note = (body.note or "").strip() or None
        shared = store.publish(
            Publication(
                document_id=document_id,
                teacher_id=user.user_id,
                version=document.version,
                basis=body.basis,
                note=note,
            ),
            sorted(set(body.class_ids)),
            to_json(prepared),
        )
        if not shared:
            # A class that is not theirs is absent, like any other.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such class.")
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="book_published",
                actor=user.user_id,
                subject=user.user_id,
                reason=f"{document_id}:{body.basis}:{len(set(body.class_ids))} class(es)",
            )
        )
        return get_publication(document_id, user.user_id)

    @app.delete(
        "/documents/{document_id}/classes/{class_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["publishing"],
    )
    def unpublish(document_id: str, class_id: str, owner: str = Depends(require_owner)) -> Response:
        """Stop sharing the book with one class. Its readers lose it on their next request."""
        owned_in(deps, document_id, owner)
        if not store.unpublish(document_id, owner, class_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not shared with that class.")
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="book_unpublished",
                actor=owner,
                subject=owner,
                reason=f"{document_id}:{class_id}",
            )
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/class-books", tags=["publishing"])
    def class_books(owner: str = Depends(require_owner)) -> list[ClassBook]:
        """Books shared with the classes this reader is an active member of."""
        positions = store.list_progress(owner)
        return [
            ClassBook(
                class_id=room.class_id,
                class_name=room.name,
                book=DocumentSummary.of(
                    document,
                    progress=positions.get(document.document_id),
                    media_type=media_type_for(
                        document.filename, store.get_source(document.document_id)
                    ),
                ),
            )
            for room, document in store.class_books(owner)
        ]
