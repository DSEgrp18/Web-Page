"""How far a book has got, and trying again when it did not get there.

A 168-page textbook takes about a minute to prepare, and a scanned one much
longer. "Preparing" with nothing moving looks exactly like "stuck", so the job
says which page it is on. And a book whose preparation failed for the
server's reasons can be started again without finding the file and uploading
it a second time.
"""

from __future__ import annotations

from dataclasses import replace

from conftest import READER, as_reader, build_pdf, sinhala_page
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app
from sinhala_reader.preparation import PreparationService, _ProgressReport
from sinhala_reader.storage import (
    REJECTED_STAGE,
    Document,
    InMemoryStore,
    Job,
    JobState,
    Store,
    new_id,
)


def _book(store: Store, *, pages: int = 1) -> tuple[Document, Job]:
    document = store.put_document(
        Document(document_id=new_id("doc"), owner=READER, filename="book.pdf", size_bytes=10)
    )
    store.put_source(document.document_id, build_pdf([sinhala_page()] * pages))
    job = store.put_job(
        Job(job_id=new_id("job"), document_id=document.document_id, owner=READER, kind="prepare")
    )
    return document, job


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Recording(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.reports: list[tuple[str, int, int]] = []

    def report_progress(self, job_id: str, stage: str, done: int, total: int) -> bool:
        self.reports.append((stage, done, total))
        return super().report_progress(job_id, stage, done, total)


# --------------------------------------------------------------------------
# Writing progress down
# --------------------------------------------------------------------------


class TestTheReport:
    def test_writes_at_most_once_a_second_within_a_stage(self) -> None:
        store = _Recording()
        clock = _Clock()
        report = _ProgressReport(store, "job_x", every=1.0, clock=clock)

        for done in range(1, 6):
            report("extracting", done, 100)
            clock.now += 0.3

        # 0.0 is the stage's first page; 1.2 is the first a second after it.
        assert store.reports == [("extracting", 1, 100), ("extracting", 5, 100)]

    def test_always_writes_a_new_stage_and_the_last_page(self) -> None:
        """So each stage is seen to begin and to end, however fast it is."""
        store = _Recording()
        report = _ProgressReport(store, "job_x", every=60.0, clock=_Clock())

        report("extracting", 1, 3)
        report("extracting", 2, 3)
        report("extracting", 3, 3)
        report("structuring", 1, 3)

        assert store.reports == [
            ("extracting", 1, 3),
            ("extracting", 3, 3),
            ("structuring", 1, 3),
        ]

    def test_a_failed_write_does_not_fail_the_book(self) -> None:
        class Broken(InMemoryStore):
            def report_progress(self, job_id: str, stage: str, done: int, total: int) -> bool:
                raise ConnectionError("the database blinked")

        _ProgressReport(Broken(), "job_x", clock=_Clock())("extracting", 1, 1)


class TestPreparationReports:
    def test_a_book_reports_its_pages_while_it_is_prepared(self) -> None:
        store = _Recording()
        document, job = _book(store, pages=3)

        PreparationService(store).run_once(document.document_id, job.job_id)

        assert ("extracting", 1, 3) in store.reports
        assert ("extracting", 3, 3) in store.reports
        assert ("structuring", 3, 3) in store.reports
        after = store.get_job(job.job_id, READER)
        assert after is not None and after.state is JobState.SUCCEEDED

    def test_the_status_says_which_page(self) -> None:
        deps = Deps(store=InMemoryStore(), run_in_background=False)
        client = TestClient(create_app(deps))
        document, job = _book(deps.store)
        deps.store.put_job(replace(job, state=JobState.RUNNING))
        deps.store.report_progress(job.job_id, "recognising", 12, 168)

        body = client.get(
            f"/documents/{document.document_id}/jobs/{job.job_id}", headers=as_reader(client)
        ).json()

        assert (body["stage"], body["pages_done"], body["pages_total"]) == ("recognising", 12, 168)
        assert body["can_retry"] is False


# --------------------------------------------------------------------------
# Trying again
# --------------------------------------------------------------------------


def _client() -> tuple[TestClient, Deps]:
    deps = Deps(store=InMemoryStore(), run_in_background=False)
    return TestClient(create_app(deps)), deps


def _failed(store: Store, stage: str = "stalled") -> tuple[Document, Job]:
    document, job = _book(store)
    return document, store.put_job(
        replace(job, state=JobState.FAILED, stage=stage, detail="it stopped")
    )


class TestTryingAgain:
    def test_a_failed_book_is_prepared_again_from_its_stored_file(self) -> None:
        client, deps = _client()
        document, failed = _failed(deps.store)

        response = client.post(
            f"/documents/{document.document_id}/retry", headers=as_reader(client)
        )

        assert response.status_code == 202
        job = response.json()["job"]
        assert job["job_id"] != failed.job_id
        # Run inline, so it has finished by the time the response arrives.
        assert job["state"] == "succeeded"
        assert response.json()["segment_count"] > 0

    def test_the_failure_stays_on_record(self) -> None:
        client, deps = _client()
        document, failed = _failed(deps.store)

        client.post(f"/documents/{document.document_id}/retry", headers=as_reader(client))

        jobs = deps.store.jobs_for(document.document_id, READER)
        assert [j.job_id for j in jobs][0] == failed.job_id
        assert jobs[0].state is JobState.FAILED
        assert len(jobs) == 2

    def test_the_library_can_tell_a_failed_book_from_one_being_prepared(self) -> None:
        """Both have no version. Without the job, both read as "preparing"
        for ever, and the library polls for ever."""
        client, deps = _client()
        failed, _ = _failed(deps.store)
        waiting, job = _book(deps.store)
        deps.store.put_job(replace(job, state=JobState.RUNNING))

        books = {
            b["document_id"]: b for b in client.get("/documents", headers=as_reader(client)).json()
        }

        assert books[failed.document_id]["job"]["state"] == "failed"
        assert books[failed.document_id]["job"]["can_retry"] is True
        assert books[waiting.document_id]["job"]["state"] == "running"

    def test_the_failed_status_offers_it(self) -> None:
        client, deps = _client()
        document, failed = _failed(deps.store)

        body = client.get(
            f"/documents/{document.document_id}/jobs/{failed.job_id}", headers=as_reader(client)
        ).json()

        assert body["can_retry"] is True

    def test_a_rejected_file_is_not_offered_again(self) -> None:
        """It would be rejected the same way; offering is a second disappointment."""
        client, deps = _client()
        document, failed = _failed(deps.store, stage=REJECTED_STAGE)

        status = client.get(
            f"/documents/{document.document_id}/jobs/{failed.job_id}", headers=as_reader(client)
        ).json()
        response = client.post(
            f"/documents/{document.document_id}/retry", headers=as_reader(client)
        )

        assert status["can_retry"] is False
        assert response.status_code == 409

    def test_a_book_being_prepared_or_ready_is_not_started_again(self) -> None:
        client, deps = _client()
        for state in (JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED):
            document, job = _book(deps.store)
            deps.store.put_job(replace(job, state=state))

            response = client.post(
                f"/documents/{document.document_id}/retry", headers=as_reader(client)
            )

            assert response.status_code == 409, state
            assert len(deps.store.jobs_for(document.document_id, READER)) == 1

    def test_another_readers_book_is_absent(self) -> None:
        client, deps = _client()
        document, _ = _failed(deps.store)

        response = client.post(
            f"/documents/{document.document_id}/retry",
            headers=as_reader(client, "someone-else"),
        )

        assert response.status_code == 404
        assert len(deps.store.jobs_for(document.document_id, READER)) == 1

    def test_a_rejected_upload_fails_as_rejected(self) -> None:
        """The file itself is the problem, so the stage says so."""
        client, _ = _client()
        broken = build_pdf([sinhala_page()])[:400]

        body = client.post(
            "/documents",
            files={"file": ("book.pdf", broken, "application/pdf")},
            headers=as_reader(client),
        ).json()

        assert (body["job"]["state"], body["job"]["stage"]) == ("failed", REJECTED_STAGE)
