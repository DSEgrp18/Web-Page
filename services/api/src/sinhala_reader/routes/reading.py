"""Pages, segments, audio, bookmarks and the reading position."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sinhala_tts.adapter import TextNotSpeakableError

from ..preparation import get_prepared
from ..schemas import (
    AudioManifest,
    BookmarkBody,
    BookmarkDetail,
    PageDetail,
    ProgressBody,
    ProgressDetail,
    SegmentDetail,
)
from ..security import require_owner
from ..storage import Bookmark, Progress, new_id
from .common import REAL_MODEL_HEADER, owned_in, prepared_or_409_in

if TYPE_CHECKING:
    from ..app import Deps


#: How many bookmarks one reader may keep in one document. CLAUDE.md asks for
#: quotas; this is the one that stops a bookmark list from becoming a place to
#: store text. Well beyond a reader marking every section of a textbook, and far
#: short of a list nobody could navigate by ear.
MAX_BOOKMARKS = 500


def register(app: FastAPI, deps: Deps) -> None:
    """Add the reading routes to ``app``, acting through ``deps``."""
    owned = partial(owned_in, deps)
    prepared_or_409 = partial(prepared_or_409_in, deps)

    # -- structure ---------------------------------------------------------

    @app.get("/documents/{document_id}/pages/{page_index}", tags=["reading"])
    def get_page(
        document_id: str, page_index: int, owner: str = Depends(require_owner)
    ) -> PageDetail:
        """One page's segments, in reading order, with what cannot be read."""
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        page = prepared.page(page_index)
        if page is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such page.")
        return PageDetail.of(page)

    @app.get("/documents/{document_id}/segments/{segment_id}", tags=["reading"])
    def get_segment(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> SegmentDetail:
        document = owned(document_id, owner)
        segment = prepared_or_409(document).segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        return SegmentDetail.of(segment)

    # -- audio -------------------------------------------------------------

    @app.get("/documents/{document_id}/segments/{segment_id}/audio", tags=["reading"])
    def get_audio(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> Response:
        """The audio for one segment, generated on demand and then cached.

        Generating on demand is what lets a reader start listening to the page
        they asked for while the rest of the book is still being prepared.
        Concurrent requests for the same segment are deduplicated, so prefetch
        and playback cannot generate it twice.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")

        assert document.version is not None
        try:
            record = deps.synthesis.synthesize(
                text=segment.display_text,
                document_id=document_id,
                owner=owner,
                segment_id=segment_id,
                document_version=document.version,
                # The text the pipeline prepared knowing the segment's role, not a
                # fresh normalisation of what is on screen: a heading's "1.1" is a
                # section number, and only the pipeline knew it was a heading.
                prepared=(segment.spoken_text, segment.model_text),
            )
        except TextNotSpeakableError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "This segment has nothing to say."
            ) from error

        return Response(
            content=record.wav,
            media_type="audio/wav",
            headers={
                REAL_MODEL_HEADER: "true" if record.is_real_model else "false",
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": f'inline; filename="{segment_id}.wav"',
            },
        )

    @app.get("/documents/{document_id}/segments/{segment_id}/audio/manifest", tags=["reading"])
    def get_audio_manifest(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> AudioManifest:
        """What produced this segment's audio, without downloading it."""
        document = owned(document_id, owner)
        segment = prepared_or_409(document).segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        assert document.version is not None
        key = deps.synthesis.cache_key_for(
            segment.display_text,
            document.version,
            prepared=(segment.spoken_text, segment.model_text),
        )
        record = deps.store.get_audio(key, document_id, owner)
        return AudioManifest(
            segment_id=segment_id,
            cache_key=key,
            generated=record is not None,
            real_model=record.is_real_model if record else deps.adapter.is_real_model,
            voice_id=record.voice_id if record else None,
            model_version=record.model_version if record else None,
            duration_seconds=record.duration_seconds if record else None,
        )

    # -- bookmarks ---------------------------------------------------------

    @app.post("/documents/{document_id}/bookmarks", tags=["reading"])
    def add_bookmark(
        document_id: str,
        body: BookmarkBody,
        response: Response,
        owner: str = Depends(require_owner),
    ) -> BookmarkDetail:
        """Mark a place worth coming back to.

        Bookmarking the same sentence twice is not an error and does not make a
        second entry — it updates the note. The control is a button pressed
        without seeing what it did, and a reader navigating a list by ear should
        not have to find and delete a duplicate they did not know they made.

        Answers 201 when the bookmark is new and 200 when it replaced one, so an
        interface can say which happened rather than guess.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(body.segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")

        existing = deps.store.list_bookmarks(document_id, owner)
        if len(existing) >= MAX_BOOKMARKS and not any(
            b.segment_id == body.segment_id for b in existing
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This document already has {MAX_BOOKMARKS} bookmarks. "
                "Remove one before adding another.",
            )

        assert document.version is not None
        note = (body.note or "").strip() or None
        bookmark, created = deps.store.put_bookmark(
            Bookmark(
                bookmark_id=new_id("bmk"),
                document_id=document_id,
                owner=owner,
                document_version=document.version,
                segment_id=body.segment_id,
                note=note,
            )
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return BookmarkDetail.of(bookmark, segment=segment, current_version=document.version)

    @app.get("/documents/{document_id}/bookmarks", tags=["reading"])
    def list_bookmarks(
        document_id: str, owner: str = Depends(require_owner)
    ) -> list[BookmarkDetail]:
        """This reader's bookmarks, in the order they appear in the book.

        Reading order rather than the order they were made: this is a way to
        move through a document, and a list that jumps back and forth is one a
        reader has to hold in their head rather than step down.

        The sentences come from the document as it stands. A bookmark whose
        segment is no longer there is still listed — losing it silently would
        leave a reader wondering what they had marked — but it is marked as not
        found rather than described with text that is not its own.
        """
        document = owned(document_id, owner)
        # Deliberately not prepared_or_409: a reader whose book is being
        # re-extracted should still be able to see what they marked, even if the
        # sentences cannot be filled in yet.
        prepared = get_prepared(deps.store, document_id)
        bookmarks = deps.store.list_bookmarks(document_id, owner)
        details = [
            BookmarkDetail.of(
                bookmark,
                segment=prepared.segment(bookmark.segment_id) if prepared else None,
                current_version=document.version,
            )
            for bookmark in bookmarks
        ]
        positions = (
            {s.segment_id: s.index for s in prepared.segments} if prepared is not None else {}
        )
        # Anything that cannot be placed in the book goes last, oldest first,
        # rather than being dropped into the middle at an arbitrary point.
        return sorted(
            details,
            key=lambda d: (
                (0, positions[d.segment_id], "")
                if d.segment_id in positions
                else (1, 0, d.created_at)
            ),
        )

    @app.delete(
        "/documents/{document_id}/bookmarks/{bookmark_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["reading"],
    )
    def delete_bookmark(
        document_id: str, bookmark_id: str, owner: str = Depends(require_owner)
    ) -> Response:
        owned(document_id, owner)
        bookmark = deps.store.get_bookmark(bookmark_id, owner)
        if bookmark is None or bookmark.document_id != document_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bookmark.")
        deps.store.delete_bookmark(bookmark_id, owner)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # -- reading position --------------------------------------------------

    @app.put("/documents/{document_id}/progress", tags=["reading"])
    def save_progress(
        document_id: str, body: ProgressBody, owner: str = Depends(require_owner)
    ) -> ProgressDetail:
        """Remember where the reader is, against the version they were reading.

        Storing the version matters: text corrected since is a different
        document, and dropping the reader at the same segment id in changed
        text would put them somewhere they never were.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(body.segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        assert document.version is not None
        progress = deps.store.put_progress(
            Progress(
                document_id=document_id,
                owner=owner,
                document_version=document.version,
                segment_id=body.segment_id,
                offset_seconds=body.offset_seconds,
                # Resolved here, while the prepared document is already loaded
                # to check the segment exists. The library reads it back to draw
                # a progress bar without loading anything.
                segment_index=segment.index,
            )
        )
        return ProgressDetail.of(progress, current_version=document.version)

    @app.get("/documents/{document_id}/progress", tags=["reading"])
    def read_progress(document_id: str, owner: str = Depends(require_owner)) -> ProgressDetail:
        document = owned(document_id, owner)
        progress = deps.store.get_progress(document_id, owner)
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No saved position.")
        return ProgressDetail.of(progress, current_version=document.version)
