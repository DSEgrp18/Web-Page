"""Voicing a shared book once, ahead of time, for the whole class.

A class of thirty pressing play on the same chapter should not wait for the
same sentence thirty times, nor queue thirty requests behind one voice. So a
teacher who has shared a book can have every sentence of the version the class
reads voiced in advance, into the book's own audio (one recording per book, as
the audio route already makes it), and the class then plays from the cache.

There is no job row. How far it has got is read from the audio cache, which is
right whichever process made the audio and survives a restart, and a run that
stops part-way is resumed by starting it again: every sentence already voiced
is a cache hit and costs nothing. Withheld pages are skipped, as they are for
the class. A book that stops being shared stops being voiced.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from sinhala_documents.pipeline import ReadableSegment
from sinhala_documents.serialise import UnreadableFormat, from_json
from sinhala_tts.adapter import TextNotSpeakableError

from .audio import SynthesisService
from .storage import PageDecision, Store

log = logging.getLogger(__name__)

#: How often a run checks that the book is still shared, in sentences.
RECHECK_EVERY = 25


@dataclass(frozen=True)
class ClassEdition:
    """The sentences the class hears: the pinned version, withheld pages left out."""

    version: str
    segments: tuple[ReadableSegment, ...]


def class_edition(store: Store, document_id: str, owner: str) -> ClassEdition | None:
    """What a class reads of this owner's book, or ``None`` if it is not shared."""
    found = store.publication(document_id, owner)
    if found is None:
        return None
    publication, _ = found
    payload = store.get_prepared_version(document_id, publication.version)
    if payload is None:
        return None
    try:
        prepared = from_json(payload)
    except (UnreadableFormat, ValueError, KeyError):
        return None
    withheld = {
        index
        for index, decision in store.page_reviews(document_id, owner, publication.version).items()
        if decision == PageDecision.WITHHELD
    }
    return ClassEdition(
        version=publication.version,
        segments=tuple(
            segment
            for page in prepared.pages
            if page.page_index not in withheld
            for segment in page.segments
            # A sentence with nothing to say is never voiced, so never waited for.
            if segment.spoken_text.strip()
        ),
    )


@dataclass(frozen=True)
class Progress:
    version: str
    total: int
    ready: int


def progress(
    store: Store, synthesis: SynthesisService, document_id: str, owner: str
) -> Progress | None:
    """How many of the class's sentences already have audio."""
    edition = class_edition(store, document_id, owner)
    if edition is None:
        return None
    have = store.audio_keys(document_id, owner)
    ready = sum(
        1
        for segment in edition.segments
        if synthesis.cache_key_for(
            segment.display_text,
            edition.version,
            prepared=(segment.spoken_text, segment.model_text),
        )
        in have
    )
    return Progress(version=edition.version, total=len(edition.segments), ready=ready)


def run(store: Store, synthesis: SynthesisService, document_id: str, owner: str) -> int:
    """Voice every sentence the class will hear. Returns how many were attempted.

    Safe to run twice, or twice at once: the synthesis service deduplicates
    per sentence, and anything already voiced is read from the cache.
    """
    edition = class_edition(store, document_id, owner)
    if edition is None:
        return 0
    done = 0
    for done, segment in enumerate(edition.segments, start=1):
        if done % RECHECK_EVERY == 0 and store.publication(document_id, owner) is None:
            log.info("prerender stopped: %s is no longer shared", document_id)
            break
        try:
            synthesis.synthesize(
                text=segment.display_text,
                document_id=document_id,
                owner=owner,
                segment_id=segment.segment_id,
                document_version=edition.version,
                prepared=(segment.spoken_text, segment.model_text),
            )
        except TextNotSpeakableError:
            continue
    return done


Dispatch = Callable[[str, str], None]


class Prerenderer:
    """Starts runs where the deployment says work runs: inline, a thread, or the queue."""

    def __init__(
        self, store: Store, synthesis: SynthesisService, dispatch: Dispatch | None = None
    ) -> None:
        self._store = store
        self._synthesis = synthesis
        self._dispatch = dispatch or self._in_thread
        self._running: set[str] = set()
        self._guard = threading.Lock()

    def inline(self, document_id: str, owner: str) -> None:
        run(self._store, self._synthesis, document_id, owner)

    def _in_thread(self, document_id: str, owner: str) -> None:
        with self._guard:
            if document_id in self._running:
                return  # One run per book per process; another would only wait.
            self._running.add(document_id)

        def runner() -> None:
            try:
                run(self._store, self._synthesis, document_id, owner)
            except Exception:  # A thread has no caller to tell; the log does.
                log.exception("prerender failed for %s", document_id)
            finally:
                with self._guard:
                    self._running.discard(document_id)

        threading.Thread(target=runner, daemon=True, name=f"prerender-{document_id}").start()

    def start(self, document_id: str, owner: str) -> None:
        self._dispatch(document_id, owner)
