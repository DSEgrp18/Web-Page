"""What to save for listening offline: one chapter's sentences and their audio.

The manifest lists every sentence in the chapter and says which already have
audio. The browser saves only those, into a cache it clears on sign-out, and
says how many are missing: offline there is no voice to make the rest, and a
chapter with silent gaps must say so rather than skip them unannounced.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field

from ..security import require_owner
from .common import prepared_for_in, readable_in

if TYPE_CHECKING:
    from ..app import Deps

#: A chapter bigger than this is saved in parts: a download a phone gives up on
#: halfway is worse than two that finish.
MAX_CLIPS = 600


class OfflineClip(BaseModel):
    segment_id: str
    page_index: int
    page_label: str | None
    text: str
    ready: bool = Field(description="Audio exists and can be saved now.")


class OfflineManifest(BaseModel):
    document_id: str
    version: str
    title: str
    chapter: str | None = Field(description="Null for a book without chapters.")
    first_page: int
    last_page: int
    clips: list[OfflineClip]
    ready: int
    total: int
    truncated: bool = Field(description="The chapter was longer than one download holds.")


def register(app: FastAPI, deps: Deps) -> None:
    """Add the offline manifest route to ``app``, acting through ``deps``."""

    @app.get("/documents/{document_id}/offline", tags=["reading"])
    def offline_manifest(
        document_id: str,
        page: int = Query(ge=0, description="Any page of the chapter to save."),
        reader: str = Depends(require_owner),
    ) -> OfflineManifest:
        """The chapter containing ``page``, or the whole book if it has no chapters."""
        reading = readable_in(deps, document_id, reader)
        prepared = prepared_for_in(deps, reading)
        assert prepared is not None
        document = reading.document
        pages = [p.page_index for p in prepared.pages]
        last_page = max(pages, default=0)
        first, last, chapter = 0, last_page, None
        opens = sorted(prepared.chapters or (), key=lambda c: c.page_index)
        for position, found in enumerate(opens):
            if found.page_index <= page:
                first, chapter = found.page_index, found.title
                following = opens[position + 1] if position + 1 < len(opens) else None
                last = following.page_index - 1 if following else last_page
        if opens and page < opens[0].page_index:
            first, last, chapter = 0, opens[0].page_index - 1, None

        have = deps.store.audio_keys(document_id, document.owner)
        segments = [s for s in prepared.segments if first <= s.page_index <= last]
        clips = [
            OfflineClip(
                segment_id=s.segment_id,
                page_index=s.page_index,
                page_label=s.page_label,
                text=s.display_text,
                ready=deps.synthesis.cache_key_for(
                    s.display_text, prepared.version, prepared=(s.spoken_text, s.model_text)
                )
                in have,
            )
            for s in segments[:MAX_CLIPS]
        ]
        return OfflineManifest(
            document_id=document_id,
            version=prepared.version,
            title=(document.title or "").strip() or document.filename,
            chapter=chapter,
            first_page=first,
            last_page=last,
            clips=clips,
            ready=sum(c.ready for c in clips),
            total=len(clips),
            truncated=len(segments) > MAX_CLIPS,
        )
