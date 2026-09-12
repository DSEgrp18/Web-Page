"""Preparation on a real broker, with a real worker.

Celery has an eager mode that runs tasks in the caller. It is useful and it
proves almost nothing that matters here: the interesting claims are that a task
crosses a process boundary, that a redelivered task does not redo finished work,
and that a transient failure is retried a bounded number of times and then
reported. Eager mode short-circuits all three.

So these start an actual worker against an actual Redis, and skip loudly when
there is not one. CLAUDE.md: mocks alone do not validate integration.

The unit tests at the bottom need no broker — they cover configuration mistakes,
which are the failures most likely to reach a deployment.
"""

from __future__ import annotations

import importlib
import os
import threading
from pathlib import Path

import pytest
from conftest import READER, as_reader, upload
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app
from sinhala_reader.preparation import PreparationService, TransientFailure
from sinhala_reader.queue import (
    CELERY,
    MAX_RETRIES,
    QUEUE_ENV,
    REDIS_URL_ENV,
    THREAD,
    broker_url,
    build_app,
    queue_mode,
    send_prepare,
    uses_celery,
)
from sinhala_reader.storage import Document, InMemoryStore, Job, JobState, new_id

REDIS_URL = os.environ.get(REDIS_URL_ENV)

needs_redis = pytest.mark.skipif(
    not REDIS_URL,
    reason=(
        f"No {REDIS_URL_ENV}. The queue was not exercised against a real broker. "
        "See services/api/README.md."
    ),
)


# --- configuration, which needs nothing running -----------------------------


class TestChoosingADispatcher:
    def test_a_thread_is_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A test run and a --reload must not need a broker."""
        monkeypatch.delenv(QUEUE_ENV, raising=False)

        assert queue_mode() == THREAD
        assert uses_celery() is False

    def test_an_unknown_dispatcher_stops_the_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A typo must not quietly select the one without durability.

        The same rule as the voice adapter: a deployment variable that is nearly
        right has to fail loudly, because nothing about the running server would
        look wrong afterwards.
        """
        monkeypatch.setenv(QUEUE_ENV, "celary")

        with pytest.raises(ValueError, match="celary"):
            queue_mode()

    def test_the_queue_without_a_broker_refuses_to_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The operator believes work is durable. It must be, or they must be told.

        Degrading silently to a thread here is the worst option: the deployment
        reports the queue it was configured with and loses work anyway.
        """
        monkeypatch.setenv(QUEUE_ENV, CELERY)
        monkeypatch.delenv(REDIS_URL_ENV, raising=False)

        with pytest.raises(ValueError, match=REDIS_URL_ENV):
            broker_url()

    def test_readiness_says_a_thread_is_not_a_queue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(QUEUE_ENV, raising=False)
        client = TestClient(
            create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
        )

        body = client.get("/readiness").json()

        assert body["queue"] == THREAD
        assert any("runs in a thread" in note for note in body["limitations"])


# --- idempotency, which needs no broker either ------------------------------


def a_queued_job(store, document_id: str) -> Job:
    return store.put_job(
        Job(job_id=new_id("job"), document_id=document_id, owner=READER, kind="prepare")
    )


class TestRunningTwice:
    """Late acknowledgement makes redelivery normal, not exceptional."""

    def test_a_finished_job_does_no_work_again(self, book: bytes) -> None:
        """Re-extracting would spend another 26 seconds to produce the same pages."""
        deps = Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False)
        client = TestClient(create_app(deps))
        document_id = upload(client, book).json()["document_id"]
        job_id = deps.store.jobs_for(document_id, READER)[0].job_id
        before = deps.store.get_job(job_id, READER)
        assert before is not None and before.state is JobState.SUCCEEDED

        deps.preparation.run_once(document_id, job_id)

        after = deps.store.get_job(job_id, READER)
        assert after is not None
        assert after.state is JobState.SUCCEEDED
        # Untouched, not merely still successful: a second run would have
        # stamped updated_at even if it produced the same pages.
        assert after.updated_at == before.updated_at

    def test_a_cancelled_job_is_not_resurrected(self) -> None:
        """The reader deleted the document. Redelivery must not undo that."""
        store = InMemoryStore()
        service = PreparationService(store)
        document = store.put_document(
            Document(document_id=new_id("doc"), owner=READER, filename="b.pdf", size_bytes=10)
        )
        job = a_queued_job(store, document.document_id)
        store.put_job(Job(**{**vars(job), "state": JobState.CANCELLED, "stage": "cancelled"}))

        service.run_once(document.document_id, job.job_id)

        got = store.get_job(job.job_id, READER)
        assert got is not None and got.state is JobState.CANCELLED

    def test_a_vanished_job_is_not_an_error(self) -> None:
        """A task can outlive the job it names; that is not worth a stack trace."""
        service = PreparationService(InMemoryStore())

        service.run_once("doc_gone", "job_gone")  # must simply return


class TestFailures:
    def test_a_rejected_document_fails_without_retrying(self) -> None:
        """The same file is rejected the same way every time.

        A reader watching four attempts learns nothing from the extra three, and
        the message is about their file rather than about the server.
        """
        store = InMemoryStore()
        service = PreparationService(store)
        document = store.put_document(
            Document(document_id=new_id("doc"), owner=READER, filename="b.pdf", size_bytes=10)
        )
        store.put_source(document.document_id, b"this is not a pdf" + b"\x00" * 2000)
        job = a_queued_job(store, document.document_id)

        service.run_once(document.document_id, job.job_id)  # no exception

        got = store.get_job(job.job_id, READER)
        assert got is not None and got.state is JobState.FAILED

    def test_an_unexpected_failure_is_raised_for_the_caller_to_decide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A thread fails the job; a queue retries first.

        Deciding that inside the service would mean the thread path silently
        swallowing what the queue path recovers from.
        """
        import sinhala_reader.preparation as preparation

        def explode(_source, **_settings):
            raise OSError("the disk went away")

        monkeypatch.setattr(preparation, "prepare_document", explode)

        store = InMemoryStore()
        service = PreparationService(store)
        document = store.put_document(
            Document(document_id=new_id("doc"), owner=READER, filename="b.pdf", size_bytes=10)
        )
        store.put_source(document.document_id, b"%PDF-1.7")
        job = a_queued_job(store, document.document_id)

        with pytest.raises(TransientFailure) as raised:
            service.run_once(document.document_id, job.job_id)

        # No document text in it, and no path either. CLAUDE.md forbids private
        # passages in logs, and a failure message reaches a screen as well.
        assert "OSError" in raised.value.detail
        assert "disk went away" not in raised.value.detail

    def test_failing_a_job_that_already_finished_changes_nothing(self, book: bytes) -> None:
        """Exhausted retries must not overwrite a success another attempt got."""
        deps = Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False)
        client = TestClient(create_app(deps))
        document_id = upload(client, book).json()["document_id"]
        job_id = deps.store.jobs_for(document_id, READER)[0].job_id

        deps.preparation.fail(document_id, job_id, stage="extracting", detail="too late")

        got = deps.store.get_job(job_id, READER)
        assert got is not None and got.state is JobState.SUCCEEDED


# --- a real broker and a real worker ----------------------------------------


@needs_redis
class TestOnARealBroker:
    @pytest.fixture
    def celery_app(self):
        app = build_app(REDIS_URL)
        # Every test gets its own queue, so a task left behind by one cannot be
        # picked up by the next and make a passing run look like a failing one.
        app.conf.task_default_queue = f"test-{new_id('q')}"
        return app

    def test_a_task_crosses_into_a_worker_and_prepares_the_book(
        self, celery_app, book: bytes
    ) -> None:
        """The claim the whole change rests on: another process does the work."""
        from celery.contrib.testing.worker import start_worker

        store = InMemoryStore()
        document = store.put_document(
            Document(
                document_id=new_id("doc"),
                owner=READER,
                filename="b.pdf",
                size_bytes=len(book),
            )
        )
        store.put_source(document.document_id, book)
        job = a_queued_job(store, document.document_id)

        # The worker runs in this process but on its own thread, consuming from
        # the real broker. A separate OS process would need the store to be
        # Postgres; that path is covered by test_postgres_routes.py.
        import sinhala_reader.queue as queue_module

        queue_module.build_store = lambda: store

        with start_worker(celery_app, perform_ping_check=False, shutdown_timeout=60):
            send_prepare(celery_app, document.document_id, job.job_id)
            _wait_for(lambda: _state(store, job.job_id) is JobState.SUCCEEDED)

        got = store.get_document(document.document_id, READER)
        assert got is not None and got.version is not None
        assert got.segment_count > 0
        assert store.get_prepared(document.document_id) is not None

    def test_upload_returns_immediately_and_the_worker_finishes_it(
        self, celery_app, book: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What a reader actually experiences: 202 now, pages shortly after."""
        from celery.contrib.testing.worker import start_worker

        monkeypatch.setenv(QUEUE_ENV, CELERY)
        monkeypatch.setenv(REDIS_URL_ENV, REDIS_URL or "")

        store = InMemoryStore()
        import sinhala_reader.queue as queue_module

        queue_module.build_store = lambda: store

        # Deps builds its own Celery app from the environment, and the
        # dispatcher closes over it. Replacing deps.celery afterwards changes
        # nothing the dispatcher uses - which is how this test first failed,
        # publishing to the default queue while the worker listened on another.
        deps = Deps(store=store, warm_on_start=False)
        assert deps.celery is not None, "the queue should have been selected"
        deps.celery.conf.task_default_queue = celery_app.conf.task_default_queue

        client = TestClient(create_app(deps))

        with start_worker(deps.celery, perform_ping_check=False, shutdown_timeout=60):
            response = upload(client, book)
            assert response.status_code == 202
            document_id = response.json()["document_id"]
            job_id = deps.store.jobs_for(document_id, READER)[0].job_id

            _wait_for(lambda: _state(store, job_id) is JobState.SUCCEEDED)

        page = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client))
        assert page.status_code == 200


def _state(store, job_id: str) -> JobState | None:
    job = store.get_job_for_worker(job_id)
    return job.state if job else None


def _wait_for(condition, timeout: float = 60.0) -> None:
    """Poll until true, or fail saying what never happened.

    A bare sleep would either be too short on a loaded machine or waste a minute
    on every run; a timeout that raises tells you it hung rather than leaving
    the next assertion to fail confusingly.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.1)
    raise AssertionError(f"condition never became true within {timeout}s")


# --- retries ----------------------------------------------------------------


@needs_redis
def test_a_transient_failure_is_retried_and_then_reported(
    monkeypatch: pytest.MonkeyPatch, book: bytes
) -> None:
    """Bounded retries, then an answer.

    CLAUDE.md asks for bounded retries. Unbounded would re-extract a broken
    document for ever at 26 seconds a time while the reader watches a job that
    never resolves — which is worse than being told it failed.
    """
    from celery.contrib.testing.worker import start_worker

    import sinhala_reader.preparation as preparation
    import sinhala_reader.queue as queue_module

    app = build_app(REDIS_URL)
    app.conf.task_default_queue = f"test-{new_id('q')}"

    store = InMemoryStore()
    document = store.put_document(
        Document(document_id=new_id("doc"), owner=READER, filename="b.pdf", size_bytes=len(book))
    )
    store.put_source(document.document_id, book)
    job = a_queued_job(store, document.document_id)

    # Counted, not inferred. Asserting that the failure message mentions a
    # number proves only that this file writes that number into the message;
    # counting extractions proves the work was actually attempted again.
    attempts: list[int] = []
    counting = threading.Lock()

    def always_fails(_source, **_settings):
        with counting:
            attempts.append(1)
        raise OSError("storage is having a moment")

    monkeypatch.setattr(preparation, "prepare_document", always_fails)
    queue_module.build_store = lambda: store
    # Retry immediately rather than after 5, 10 and 20 seconds.
    monkeypatch.setattr(queue_module, "RETRY_BACKOFF", 0)

    with start_worker(app, perform_ping_check=False, shutdown_timeout=120):
        send_prepare(app, document.document_id, job.job_id)
        _wait_for(lambda: _state(store, job.job_id) is JobState.FAILED, timeout=120)

    got = store.get_job(job.job_id, READER)
    assert got is not None
    assert got.state is JobState.FAILED
    assert len(attempts) == MAX_RETRIES + 1, (
        f"expected one attempt plus {MAX_RETRIES} retries, got {len(attempts)}"
    )
    # And the reader is told, rather than left with a bare failure.
    assert str(MAX_RETRIES) in (got.detail or "")
    assert "OSError" in (got.detail or "")
    assert "storage is having a moment" not in (got.detail or "")


def test_the_celery_entry_point_resolves_to_an_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """What a worker container actually runs, pinned because it was wrong once.

    "-A sinhala_reader.queue:build_app" looks reasonable and does not work:
    Celery's find_app returns whatever the name resolves to and never calls it,
    so a factory reference hands Celery a function. The container started, the
    worker did not, and nothing in the test suite would have noticed.
    """
    pytest.importorskip("celery")
    from celery.app.utils import find_app

    monkeypatch.setenv(REDIS_URL_ENV, "redis://127.0.0.1:6379/0")
    import sinhala_reader.celery_worker as entry_point

    importlib.reload(entry_point)

    app = find_app("sinhala_reader.celery_worker")
    assert app.main == "sinhala_reader"
    assert "sinhala_reader.prepare_document" in app.tasks


def test_importing_the_queue_module_does_not_import_celery() -> None:
    """Celery is an extra. The interface contributor must not need a broker library."""
    source = (
        Path(__file__).resolve().parents[1] / "src" / "sinhala_reader" / "queue.py"
    ).read_text(encoding="utf-8")
    module_level = [
        line for line in source.splitlines() if line.startswith(("import celery", "from celery"))
    ]
    assert module_level == []
