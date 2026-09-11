"""Document preparation on Celery, so work survives the process that accepted it.

The last of the three stopgaps in ``services/api/README.md``. A thread gave the
right job states and the right failure reporting, and it was honest about what
it could not do: if the server stopped while a book was being extracted, the job
stayed ``running`` for ever and nobody was ever going to finish it. A reader
waiting on a 168-page textbook had no way to tell that from slow progress.

**Why a queue changes anything here.** Extraction takes about 26 seconds and
happens exactly when a reader is waiting to start. A thread ties that work to
one process, so a deploy in the middle of it loses the work *and* leaves the
reader's job stuck. A broker outlives the process: an unacknowledged task is
redelivered and finished by whoever picks it up.

**Late acknowledgement is the setting that makes that true**, and it is the one
worth understanding before changing anything here. By default Celery marks a
task done as soon as a worker accepts it; a worker killed mid-extraction would
take the task with it. ``task_acks_late`` moves the acknowledgement to *after*
the work, so a killed worker's task goes back on the queue. The cost is that a
task can run twice, which is why the work below is idempotent rather than
merely careful.

**What is not here.** Audio synthesis stays on the request path: it is generated
per segment on demand, the reader is waiting for that specific clip, and a queue
would add latency to the thing the 5-second target is measured on. Rendering a
whole chapter ahead of time is a queued job and belongs here — that is issue #32
and it is not built yet.
"""

from __future__ import annotations

import os

from .preparation import PreparationService, TransientFailure
from .storage import build_store

#: Where the broker is. Unset means no queue: preparation runs in a thread, as
#: it did before, and ``/readiness`` says so.
REDIS_URL_ENV = "SINHALA_READER_REDIS_URL"

#: Which dispatcher preparation uses. ``thread`` is the default because a test
#: run, a ``--reload`` and a contributor building the reader interface must not
#: need a broker and a second process.
QUEUE_ENV = "SINHALA_READER_QUEUE"
THREAD = "thread"
CELERY = "celery"
MODES = (THREAD, CELERY)

#: How many times a transient failure is retried before the job is failed for
#: good. Bounded, because CLAUDE.md asks for bounded retries and because a
#: genuinely broken document would otherwise be re-extracted for ever at 26
#: seconds a time while the reader watches a job that never resolves.
MAX_RETRIES = 3

#: Seconds before the first retry, doubling. A transient failure is usually a
#: database or storage hiccup, and hammering it immediately makes it worse.
RETRY_BACKOFF = 5

#: Longer than the 26 seconds a 168-page book takes, with room for a slower
#: machine and a bigger book. A task that exceeds it is killed rather than left
#: holding a worker, and the redelivery is what gets the reader an answer.
TASK_TIME_LIMIT = 15 * 60
SOFT_TIME_LIMIT = TASK_TIME_LIMIT - 60


def queue_mode() -> str:
    """Which dispatcher is configured. Unknown values stop the process."""
    mode = os.environ.get(QUEUE_ENV, THREAD).strip() or THREAD
    if mode not in MODES:
        raise ValueError(
            f"{QUEUE_ENV}={mode!r} is not a dispatcher this server knows. "
            f"Use one of: {', '.join(MODES)}."
        )
    return mode


def uses_celery() -> bool:
    return queue_mode() == CELERY


def broker_url() -> str:
    """The broker, or a clear failure.

    Selecting the queue without configuring a broker is a deployment mistake
    that must not degrade quietly into running everything in a thread: the
    operator believes work is durable and it is not.
    """
    url = os.environ.get(REDIS_URL_ENV, "").strip()
    if not url:
        raise ValueError(
            f"{QUEUE_ENV}={CELERY} needs {REDIS_URL_ENV} set to a broker, "
            "for example redis://localhost:6379/0."
        )
    return url


def build_app(url: str | None = None):
    """The Celery application. Imported lazily so celery stays an extra.

    A contributor working on the reader interface should not need a broker
    library installed to run the API's tests, so nothing at module import time
    depends on Celery being present.
    """
    from celery import Celery

    app = Celery("sinhala_reader", broker=url or broker_url())
    app.conf.update(
        # See the module docstring: this is what makes a killed worker's task
        # come back rather than vanish.
        task_acks_late=True,
        # And this is the other half. Without it, a worker that dies without
        # acknowledging leaves its task invisible until the broker's visibility
        # timeout expires, which for a 26-second job reads as a hang.
        task_reject_on_worker_lost=True,
        # One book at a time per worker. Extraction is CPU-bound and pdfplumber
        # is not cheap; prefetching four books to one worker leaves three
        # readers waiting behind a queue that looks empty.
        worker_prefetch_multiplier=1,
        task_time_limit=TASK_TIME_LIMIT,
        task_soft_time_limit=SOFT_TIME_LIMIT,
        # No result backend. The job row in the database is the record a reader
        # polls; a second copy of the same state in Redis is one more thing to
        # disagree with it.
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    _register(app)
    return app


def _register(app) -> None:
    @app.task(
        name="sinhala_reader.prepare_document",
        bind=True,
        max_retries=MAX_RETRIES,
        # Only what this call needs. The task takes ids, never the document, so
        # no private content is serialised into a broker that is not the
        # database and may be retained differently.
        acks_late=True,
    )
    def prepare_document(self, document_id: str, job_id: str) -> None:
        """Extract one document. Safe to run more than once.

        Late acknowledgement means redelivery is normal rather than
        exceptional, so this has to be idempotent: a job that already reached a
        final state does no work and returns.
        """
        # A fresh store per task: the worker is another process, and it has
        # no request and no caller to inherit one from.
        service = PreparationService(build_store())
        try:
            service.run_once(document_id, job_id)
        except TransientFailure as failure:
            if self.request.retries >= MAX_RETRIES:
                # Out of attempts. The reader is told it failed rather than left
                # watching a job that will never move again.
                service.fail(
                    document_id,
                    job_id,
                    stage=failure.stage,
                    detail=f"{failure.detail} after {MAX_RETRIES} retries",
                )
                return
            raise self.retry(
                exc=failure,
                countdown=RETRY_BACKOFF * (2**self.request.retries),
            ) from failure


def send_prepare(app, document_id: str, job_id: str) -> None:
    app.send_task("sinhala_reader.prepare_document", args=[document_id, job_id])
