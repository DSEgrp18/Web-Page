"""A job whose process has died is failed as stalled, not left "running".

One job said "running" for eight days. The process preparing it had gone away,
nothing noticed, and a reader was told the whole time that their book was
still being prepared. A running job now holds a lease its process keeps
renewing; once the renewals stop, the job is failed and the reader is told.

The store's half of this is in ``test_store_contract.py``. These tests cover
the half a reader meets: the lease being held and let go by real preparation,
the heartbeat and the reaper running on real threads, and what the job route
says afterwards.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from conftest import READER, as_reader, build_pdf, sinhala_page
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app, preparation
from sinhala_reader.preparation import (
    LEASE_SECONDS,
    STALLED_DETAIL,
    PreparationService,
    TransientFailure,
    _heartbeat,
    reap_periodically,
    reap_stalled_jobs,
)
from sinhala_reader.storage import Document, InMemoryStore, Job, JobState, Store, new_id

LONG_AGO = "2000-01-01T00:00:00+00:00"


def _eventually(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def _book(store: Store) -> tuple[Document, Job]:
    """A readable document with a queued job to prepare it."""
    document = store.put_document(
        Document(document_id=new_id("doc"), owner=READER, filename="book.pdf", size_bytes=10)
    )
    store.put_source(document.document_id, build_pdf([sinhala_page()]))
    job = store.put_job(
        Job(job_id=new_id("job"), document_id=document.document_id, owner=READER, kind="prepare")
    )
    return document, job


def _running(store: Store, lease: str | None) -> tuple[Document, Job]:
    """A job left running, as if its process had died mid-work."""
    document, job = _book(store)
    return document, store.put_job(replace(job, state=JobState.RUNNING, lease_expires_at=lease))


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TestPreparationHoldsALease:
    def test_while_extracting_the_job_holds_a_live_lease(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = InMemoryStore()
        document, job = _book(store)
        seen: list[Job | None] = []
        real = preparation.prepare_document

        def watching(*args, **kwargs):  # type: ignore[no-untyped-def]
            seen.append(store.get_job(job.job_id, READER))
            return real(*args, **kwargs)

        monkeypatch.setattr(preparation, "prepare_document", watching)

        PreparationService(store).run_once(document.document_id, job.job_id)

        (during,) = seen
        assert during is not None and during.state is JobState.RUNNING
        assert during.lease_expires_at is not None and during.lease_expires_at > _now()

    def test_a_finished_job_lets_its_lease_go(self) -> None:
        store = InMemoryStore()
        document, job = _book(store)

        PreparationService(store).run_once(document.document_id, job.job_id)

        after = store.get_job(job.job_id, READER)
        assert after is not None and after.state is JobState.SUCCEEDED
        assert after.lease_expires_at is None

    def test_a_transient_failure_keeps_a_full_lease_for_the_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The job stays running while the queue waits to retry it.

        Its lease must cover that wait, or a slow broker would let the reaper
        fail a job that is only between attempts.
        """
        store = InMemoryStore()
        document, job = _book(store)

        def failing(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("the database blinked")

        monkeypatch.setattr(preparation, "prepare_document", failing)

        with pytest.raises(TransientFailure):
            PreparationService(store).run_once(document.document_id, job.job_id)

        after = store.get_job(job.job_id, READER)
        assert after is not None and after.state is JobState.RUNNING
        remaining = datetime.fromisoformat(after.lease_expires_at or LONG_AGO) - datetime.now(UTC)
        assert remaining.total_seconds() > LEASE_SECONDS - 10


class TestTheHeartbeat:
    def test_it_keeps_renewing_while_the_work_runs(self) -> None:
        store = InMemoryStore()
        _, job = _running(store, LONG_AGO)

        with _heartbeat(store, job.job_id, every=0.01):
            renewed = _eventually(
                lambda: (store.get_job(job.job_id, READER).lease_expires_at or "") > _now()
            )

        assert renewed

    def test_it_cannot_revive_a_job_the_reaper_has_failed(self) -> None:
        store = InMemoryStore()
        _, job = _running(store, LONG_AGO)
        reap_stalled_jobs(store)

        with _heartbeat(store, job.job_id, every=0.01):
            time.sleep(0.1)

        after = store.get_job(job.job_id, READER)
        assert after is not None and after.state is JobState.FAILED


class TestAReaderIsTold:
    def test_a_stalled_job_reads_as_failed_with_a_reason(self) -> None:
        deps = Deps(store=InMemoryStore(), run_in_background=False)
        client = TestClient(create_app(deps))
        document, job = _running(deps.store, LONG_AGO)

        reap_stalled_jobs(deps.store)
        response = client.get(
            f"/documents/{document.document_id}/jobs/{job.job_id}", headers=as_reader(client)
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["state"], body["stage"], body["detail"]) == (
            "failed",
            "stalled",
            STALLED_DETAIL,
        )

    def test_a_job_that_is_still_alive_is_left_alone(self) -> None:
        store = InMemoryStore()
        _, job = _running(store, "2999-01-01T00:00:00+00:00")

        assert reap_stalled_jobs(store) == []
        after = store.get_job(job.job_id, READER)
        assert after is not None and after.state is JobState.RUNNING


class TestTheReaperRuns:
    def test_it_fails_a_stalled_job_in_the_background(self) -> None:
        store = InMemoryStore()
        _, job = _running(store, LONG_AGO)

        reap_periodically(store, every=0.05)

        assert _eventually(lambda: store.get_job(job.job_id, READER).state is JobState.FAILED)

    def test_inline_work_starts_no_reaper(self) -> None:
        """A job run inline cannot outlive the request that ran it.

        So the route tests, which all run work inline, leave no thread behind.
        """
        deps = Deps(store=InMemoryStore(), run_in_background=False)

        assert deps.reap_stalled is False
        assert create_app(deps).state.reaper is None

    def test_background_work_is_reaped_by_default(self) -> None:
        deps = Deps(store=InMemoryStore(), warm_on_start=False)

        assert deps.reap_stalled is True
