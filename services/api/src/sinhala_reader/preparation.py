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

Failure detail never contains document text. A stage name and an exception type
are enough to act on, and CLAUDE.md forbids private passages in logs by default;
a failure message is a log line that also reaches a screen.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from sinhala_documents import DocumentRejected
from sinhala_documents.pipeline import ReadableDocument, prepare_document

from .storage import Document, Job, JobState, Store

#: Prepared documents, keyed by document id. Segments are derived data: cheap to
#: recompute, pointless to store twice, and never written to disk here.
_PREPARED: dict[str, ReadableDocument] = {}
_PREPARED_LOCK = threading.RLock()


def cache_prepared(document_id: str, prepared: ReadableDocument) -> None:
    with _PREPARED_LOCK:
        _PREPARED[document_id] = prepared


def get_prepared(document_id: str) -> ReadableDocument | None:
    with _PREPARED_LOCK:
        return _PREPARED.get(document_id)


def forget_prepared(document_id: str) -> None:
    """Deletion must remove derived text, not only the upload."""
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

        cache_prepared(document_id, prepared)
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
