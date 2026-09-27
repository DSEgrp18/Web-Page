"""Search inside one book: its own words first, then passages about the words.

Two lists, never merged, because they answer different questions. **Exact**
matches are sentences containing what was typed, in book order. **Related**
passages are the lexical retriever's best matches, for a word the book spells
differently or a phrase split across sentences. Both come from the pages this
reader may read, so a withheld page is never found.
"""

from __future__ import annotations

import threading
import unicodedata
from collections import OrderedDict
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel
from sinhala_documents.passages import build_passages
from sinhala_documents.retrieval import LexicalIndex

from ..security import require_owner
from .common import prepared_for_in, readable_in

if TYPE_CHECKING:
    from ..app import Deps

#: Enough to step through by ear; a longer list means the words were too common.
MAX_EXACT = 50
MAX_RELATED = 5

#: Indexes kept, by document, version and withheld pages: search is typed a few
#: letters at a time, and rebuilding BM25 over a textbook per request is waste.
_INDEXES: OrderedDict[tuple, LexicalIndex] = OrderedDict()
_INDEX_LIMIT = 16
_LOCK = threading.Lock()


class SearchHit(BaseModel):
    segment_id: str
    page_index: int
    page_label: str | None
    text: str


class SearchResults(BaseModel):
    query: str
    exact: list[SearchHit]
    related: list[SearchHit]


def normalise(text: str) -> str:
    """NFC, case-folded, whitespace collapsed. Joiners are kept: they are part
    of Sinhala words, and dropping them would match a different word."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def register(app: FastAPI, deps: Deps) -> None:
    """Add the search route to ``app``, acting through ``deps``."""

    def index_for(key: tuple, prepared) -> LexicalIndex:
        with _LOCK:
            found = _INDEXES.get(key)
            if found is not None:
                _INDEXES.move_to_end(key)
                return found
        built = LexicalIndex(build_passages(prepared))
        with _LOCK:
            _INDEXES[key] = built
            while len(_INDEXES) > _INDEX_LIMIT:
                _INDEXES.popitem(last=False)
        return built

    @app.get("/documents/{document_id}/search", tags=["reading"])
    def search(
        document_id: str,
        q: str = Query(min_length=1, max_length=200),
        reader: str = Depends(require_owner),
    ) -> SearchResults:
        """Sentences containing ``q`` in book order, and the passages most about it."""
        reading = readable_in(deps, document_id, reader)
        prepared = prepared_for_in(deps, reading)
        assert prepared is not None
        wanted = normalise(q)
        exact = [
            SearchHit(
                segment_id=s.segment_id,
                page_index=s.page_index,
                page_label=s.page_label,
                text=s.display_text,
            )
            for s in prepared.segments
            if wanted and wanted in normalise(s.display_text)
        ][:MAX_EXACT]
        key = (document_id, prepared.version, tuple(sorted(reading.withheld or ())))
        related = [
            SearchHit(
                segment_id=hit.passage.segment_ids[0],
                page_index=hit.passage.page_index,
                page_label=hit.passage.page_label,
                text=hit.passage.text,
            )
            for hit in index_for(key, prepared).search(q, limit=MAX_RELATED)
            if hit.passage.segment_ids
        ]
        return SearchResults(query=q, exact=exact, related=related)
