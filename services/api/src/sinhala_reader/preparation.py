"""Preparing an uploaded document, in the background, as a job a reader can watch.

Extraction of a whole book takes tens of seconds; the Grade 11 textbook takes
about 24. Holding an HTTP connection open for that is the thing CLAUDE.md warns
against, so upload returns immediately with a job to poll.

The work runs in a thread rather than on Celery. Celery and Redis are the
intended shape and neither exists yet; a thread has the same job states, the same
progress reporting and the same failure handling, and moving to a queue changes
this file and nothing that depends on it. What a thread does **not** give is
durability — a restart loses in-flight work — and that is said in the health
report rather than left to be discovered.

The *result* is durable, though, which it was not before: a prepared document is
written to the store and only cached in memory. That is what makes a restarted
server able to open a book it already extracted, and it is the change that lets
preparation move to another process at all.

Failure detail never contains document text. A stage name and an exception type
are enough to act on, and CLAUDE.md forbids private passages in logs by default;
a failure message is a log line that also reaches a screen.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from sinhala_documents import DocumentRejected
from sinhala_documents.pipeline import ReadableDocument, prepare_document
from sinhala_documents.serialise import UnreadableFormat, from_json, to_json

from .storage import Document, Job, JobState, Store

#: Prepared documents already deserialised, keyed by document id.
#:
#: This is a **cache in front of the store**, not the record. It used to be the
#: record, and that was a defect: the pages died with the process while the
#: document row, the job state and the segment count all survived, so a restarted
#: server listed a book, called it ready, and answered "This document is not
#: ready yet (succeeded)" when a reader opened it.
#:
#: It stays because deserialising a 168-page book on every page request would be
#: wasteful, and because it is what lets a second process — a queue worker —
#: prepare a document the API can then serve.
_PREPARED: dict[str, ReadableDocument] = {}
_PREPARED_LOCK = threading.RLock()

#: How many books to keep deserialised. Small on purpose: this is a convenience,
#: and an unbounded dictionary of whole textbooks is a slow memory leak in a
#: process that is meant to stay up.
MAX_CACHED = 8


def cache_prepared(document_id: str, prepared: ReadableDocument) -> None:
    with _PREPARED_LOCK:
        _PREPARED[document_id] = prepared
        while len(_PREPARED) > MAX_CACHED:
            # Oldest first. Losing one costs a deserialisation, not a re-extraction.
            _PREPARED.pop(next(iter(_PREPARED)))


def store_prepared(store: Store, document_id: str, prepared: ReadableDocument) -> None:
    """Write the prepared document down, then cache it."""
    store.put_prepared(document_id, to_json(prepared))
    cache_prepared(document_id, prepared)


def get_prepared(store: Store, document_id: str) -> ReadableDocument | None:
    """The prepared document, from memory or from the store.

    A payload written by a build with a different format is treated as absent
    rather than guessed at: the API answers "not ready", which is true, instead
    of serving half-understood pages to someone who cannot see that they are
    wrong.
    """
    with _PREPARED_LOCK:
        cached = _PREPARED.get(document_id)
    if cached is not None:
        return cached

    payload = store.get_prepared(document_id)
    if payload is None:
        return None
    try:
        prepared = from_json(payload)
    except (UnreadableFormat, ValueError, KeyError):
        return None
    cache_prepared(document_id, prepared)
    return prepared


def forget_prepared(document_id: str) -> None:
    """Drop the cached copy.

    The stored copy goes with the document: deletion cascades in the database
    and is explicit in the in-memory store, so this only clears the cache in
    front of it.
    """
    with _PREPARED_LOCK:
        _PREPARED.pop(document_id, None)


class PreparationService:
    """Runs document preparation and keeps its job up to date."""

    def __init__(self, store: Store, *, run_in_background: bool = True) -> None:
        self._store = store
        self._run_in_background = run_in_background

    def start(self, document: Document, job: Job) -> Job:
        """Queue preparation and return the job immediately."""
        job = self._store.put_job(replace(job, state=JobState.QUEUED, stage="queued"))
        document_id, job_id = document.document_id, job.job_id

        def runner() -> None:
            self._run(document_id, job_id)

        if self._run_in_background:
            threading.Thread(target=runner, daemon=True, name=f"prepare-{job.job_id}").start()
        else:
            # Tests run this inline so a request and its work are one step, and
            # a failure surfaces as a failure rather than as a flaky poll.
            runner()
        return self._store.get_job(job.job_id, job.owner) or job

    def _fail(self, job: Job, stage: str, detail: str) -> None:
        self._store.put_job(replace(job, state=JobState.FAILED, stage=stage, detail=detail))

    def _run(self, document_id: str, job_id: str) -> None:
        job = self._store.get_job_for_worker(job_id)
        if job is None:
            return

        job = self._store.put_job(replace(job, state=JobState.RUNNING, stage="extracting"))
        source = self._store.get_source(document_id)
        document = self._store.get_document(document_id, job.owner)
        if source is None or document is None:
            # Deleted while queued. Not a failure: the reader asked for this.
            self._store.put_job(
                replace(job, state=JobState.CANCELLED, stage="cancelled", detail=None)
            )
            return

        try:
            prepared = prepare_document(source)
        except DocumentRejected as error:
            # The one case where the message is about the reader's file rather
            # than about the server, and is safe to show them.
            self._fail(job, "extracting", str(error))
            return
        except Exception as error:  # noqa: BLE001 - recorded without document text
            self._fail(job, "extracting", f"{type(error).__name__} while reading the document")
            return

        # The reader may have deleted it while extraction ran.
        if self._store.get_document(document_id, job.owner) is None:
            forget_prepared(document_id)
            self._store.put_job(replace(job, state=JobState.CANCELLED, stage="cancelled"))
            return

        # Written down before the document is marked ready. The other order
        # leaves a window where a reader is told the book is available and the
        # pages are not there yet.
        store_prepared(self._store, document_id, prepared)
        self._store.put_document(
            replace(
                document,
                version=prepared.version,
                page_count=len(prepared.pages),
                segment_count=len(prepared.segments),
                notes=prepared.notes,
            )
        )
        self._store.put_job(replace(job, state=JobState.SUCCEEDED, stage="ready", detail=None))
