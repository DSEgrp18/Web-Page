"""One suite, run against every ``Store`` implementation.

CLAUDE.md: "Run shared behavioral contract tests against real adapters where
available; mocks alone do not validate integration." So these tests are written
once, against the interface, and parametrised over the implementations. A
Postgres store that passes here behaves like the in-memory one the reader was
built against — and where it does not, this suite is where that surfaces,
rather than in a route that quietly returns the wrong reader's book.

Every test here is about **behaviour the API depends on**, not about storage
mechanics:

- ownership, which is the store's job rather than the routes'
- deletion removing everything derived, which CLAUDE.md requires
- ordering, which the library screen relies on
- byte-exactness of audio and source, because a WAV that survives a round trip
  with one byte changed is a defect no listener could diagnose

``PostgresStore`` is skipped when no database is configured, and the skip says
so out loud. A silently skipped integration test is worse than none: it reports
green for something nobody ran.
"""

from __future__ import annotations

import os

import pytest

from sinhala_reader.storage import (
    AudioRecord,
    Document,
    InMemoryStore,
    Job,
    JobState,
    Progress,
    Store,
    new_id,
)

ALICE = "alice"
BOB = "bob"


# --- the implementations under test ----------------------------------------


def _postgres_store() -> Store:
    from sinhala_reader.postgres import PostgresStore, migrate

    url = os.environ["SINHALA_READER_DATABASE_URL"]
    migrate(url)
    store = PostgresStore(url)
    store.reset_for_tests()
    return store


@pytest.fixture(
    params=[
        pytest.param("memory", id="InMemoryStore"),
        pytest.param(
            "postgres",
            id="PostgresStore",
            marks=pytest.mark.skipif(
                not os.environ.get("SINHALA_READER_DATABASE_URL"),
                reason=(
                    "No SINHALA_READER_DATABASE_URL. The Postgres half of the store "
                    "contract did not run. See services/api/README.md."
                ),
            ),
        ),
    ]
)
def store(request: pytest.FixtureRequest) -> Store:
    if request.param == "memory":
        return InMemoryStore()
    return _postgres_store()


# --- helpers ---------------------------------------------------------------


def a_document(owner: str = ALICE, **kwargs: object) -> Document:
    fields: dict[str, object] = {
        "document_id": new_id("doc"),
        "owner": owner,
        "filename": "book.pdf",
        "size_bytes": 1234,
    }
    fields.update(kwargs)
    return Document(**fields)  # type: ignore[arg-type]


def a_job(document: Document, **kwargs: object) -> Job:
    fields: dict[str, object] = {
        "job_id": new_id("job"),
        "document_id": document.document_id,
        "owner": document.owner,
        "kind": "prepare",
    }
    fields.update(kwargs)
    return Job(**fields)  # type: ignore[arg-type]


def an_audio_record(document: Document, **kwargs: object) -> AudioRecord:
    fields: dict[str, object] = {
        "cache_key": new_id("key"),
        "document_id": document.document_id,
        "owner": document.owner,
        "segment_id": "seg_1",
        "wav": b"RIFF....WAVEfake",
        "duration_seconds": 1.5,
        "is_real_model": False,
        "voice_id": "development-si-female",
        "model_version": "development-adapter",
    }
    fields.update(kwargs)
    return AudioRecord(**fields)  # type: ignore[arg-type]


# --- documents -------------------------------------------------------------


class TestDocuments:
    def test_round_trips(self, store: Store) -> None:
        document = a_document(version="v1", page_count=168, segment_count=2829)
        store.put_document(document)

        got = store.get_document(document.document_id, ALICE)

        assert got == document

    def test_notes_survive(self, store: Store) -> None:
        """The notes are what a reader is told the book lost.

        They are a tuple of strings on the way in and must be a tuple of the
        same strings on the way out; a store that returns a list, or reorders
        them, changes what the interface promises.
        """
        document = a_document(notes=("page 12 could not be read", "page 13 is an image"))
        store.put_document(document)

        got = store.get_document(document.document_id, ALICE)

        assert got is not None
        assert got.notes == ("page 12 could not be read", "page 13 is an image")

    def test_another_owner_sees_nothing(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)

        assert store.get_document(document.document_id, BOB) is None

    def test_listing_is_scoped_and_newest_first(self, store: Store) -> None:
        older = a_document(owner=ALICE, created_at="2026-01-01T00:00:00+00:00")
        newer = a_document(owner=ALICE, created_at="2026-06-01T00:00:00+00:00")
        theirs = a_document(owner=BOB)
        for document in (older, newer, theirs):
            store.put_document(document)

        listed = store.list_documents(ALICE)

        assert [d.document_id for d in listed] == [newer.document_id, older.document_id]

    def test_listing_is_empty_for_a_stranger(self, store: Store) -> None:
        store.put_document(a_document(owner=ALICE))

        assert store.list_documents("nobody") == []

    def test_put_replaces_rather_than_duplicates(self, store: Store) -> None:
        """Preparation writes the document again with its version and counts."""
        document = a_document()
        store.put_document(document)

        store.put_document(
            Document(
                document_id=document.document_id,
                owner=document.owner,
                filename=document.filename,
                size_bytes=document.size_bytes,
                created_at=document.created_at,
                version="v2",
                page_count=5,
                segment_count=40,
            )
        )

        assert len(store.list_documents(ALICE)) == 1
        got = store.get_document(document.document_id, ALICE)
        assert got is not None and got.version == "v2" and got.page_count == 5


# --- the source PDF --------------------------------------------------------


class TestSource:
    def test_round_trips_byte_for_byte(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        data = bytes(range(256)) * 40

        store.put_source(document.document_id, data)

        assert store.get_source(document.document_id) == data

    def test_absent_source_is_none(self, store: Store) -> None:
        assert store.get_source("doc_nothing") is None


# --- jobs ------------------------------------------------------------------


class TestJobs:
    def test_round_trips(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        job = a_job(document)

        stored = store.put_job(job)
        got = store.get_job(job.job_id, ALICE)

        assert got is not None
        assert got.job_id == job.job_id
        assert got.state is JobState.QUEUED
        assert got.updated_at == stored.updated_at

    def test_put_stamps_updated_at(self, store: Store) -> None:
        """``updated_at`` is the store's to set, not the caller's.

        The API shows it to a reader waiting on a book. A caller that forgot to
        update it would leave the interface saying nothing had happened for
        several minutes while the work was in fact progressing.
        """
        document = a_document()
        store.put_document(document)
        job = a_job(document, updated_at="2020-01-01T00:00:00+00:00")

        stored = store.put_job(job)

        assert stored.updated_at != "2020-01-01T00:00:00+00:00"

    def test_state_and_detail_survive(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        job = a_job(document)
        store.put_job(job)

        from dataclasses import replace

        store.put_job(
            replace(job, state=JobState.FAILED, stage="extracting", detail="The PDF is encrypted.")
        )

        got = store.get_job(job.job_id, ALICE)
        assert got is not None
        assert got.state is JobState.FAILED
        assert got.stage == "extracting"
        assert got.detail == "The PDF is encrypted."

    def test_another_owner_sees_nothing(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)
        job = a_job(document)
        store.put_job(job)

        assert store.get_job(job.job_id, BOB) is None

    def test_the_worker_reads_without_an_owner(self, store: Store) -> None:
        """The one deliberately unscoped read. See ``Store.get_job_for_worker``."""
        document = a_document(owner=ALICE)
        store.put_document(document)
        job = a_job(document)
        store.put_job(job)

        got = store.get_job_for_worker(job.job_id)

        assert got is not None and got.owner == ALICE

    def test_jobs_for_a_document_are_scoped_and_oldest_first(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        first = a_job(document, created_at="2026-01-01T00:00:00+00:00")
        second = a_job(document, created_at="2026-02-01T00:00:00+00:00")
        store.put_job(second)
        store.put_job(first)

        listed = store.jobs_for(document.document_id, ALICE)

        assert [j.job_id for j in listed] == [first.job_id, second.job_id]
        assert store.jobs_for(document.document_id, BOB) == []


# --- audio -----------------------------------------------------------------


class TestAudio:
    def test_round_trips_byte_for_byte(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        wav = bytes(range(256)) * 100
        record = an_audio_record(document, wav=wav)

        store.put_audio(record)
        got = store.get_audio(record.cache_key, ALICE)

        assert got is not None
        assert got.wav == wav
        assert got == record

    def test_cached_audio_is_still_private(self, store: Store) -> None:
        """CLAUDE.md: keep private audio access-controlled even when cached.

        The cache key is derived from text and settings, so two readers with the
        same book would otherwise collide - and one would be served the other's
        audio because it happened to be generated first.
        """
        document = a_document(owner=ALICE)
        store.put_document(document)
        record = an_audio_record(document)
        store.put_audio(record)

        assert store.get_audio(record.cache_key, BOB) is None

    def test_the_real_model_flag_survives(self, store: Store) -> None:
        """It is part of cache identity and of every response.

        A placeholder tone that came back saying it was real would be served as
        narration to a reader who cannot see the screen to check.
        """
        document = a_document()
        store.put_document(document)
        record = an_audio_record(document, is_real_model=True, model_version="ce18fe82442ccbd3")
        store.put_audio(record)

        got = store.get_audio(record.cache_key, ALICE)

        assert got is not None and got.is_real_model is True
        assert got.model_version == "ce18fe82442ccbd3"

    def test_a_missing_key_is_none(self, store: Store) -> None:
        assert store.get_audio("key_nothing", ALICE) is None


# --- progress --------------------------------------------------------------


class TestProgress:
    def test_round_trips(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        progress = Progress(
            document_id=document.document_id,
            owner=ALICE,
            document_version="v1",
            segment_id="seg_9",
            offset_seconds=12.5,
        )

        store.put_progress(progress)
        got = store.get_progress(document.document_id, ALICE)

        assert got == progress

    def test_one_position_per_reader_per_document(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        base = Progress(
            document_id=document.document_id,
            owner=ALICE,
            document_version="v1",
            segment_id="seg_1",
        )
        store.put_progress(base)

        from dataclasses import replace

        store.put_progress(replace(base, segment_id="seg_40", offset_seconds=3.0))

        got = store.get_progress(document.document_id, ALICE)
        assert got is not None and got.segment_id == "seg_40"

    def test_readers_do_not_share_a_position(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)
        store.put_progress(
            Progress(
                document_id=document.document_id,
                owner=ALICE,
                document_version="v1",
                segment_id="seg_1",
            )
        )

        assert store.get_progress(document.document_id, BOB) is None


# --- deletion --------------------------------------------------------------


class TestDeletion:
    def test_removes_everything_derived(self, store: Store) -> None:
        """CLAUDE.md requires deletion to remove derived text, audio and caches.

        Anything left behind is private content that outlived the reader's
        decision to delete it, and the reader has no way to find out.
        """
        document = a_document()
        store.put_document(document)
        store.put_source(document.document_id, b"%PDF-1.7 ...")
        job = a_job(document)
        store.put_job(job)
        record = an_audio_record(document)
        store.put_audio(record)
        store.put_progress(
            Progress(
                document_id=document.document_id,
                owner=ALICE,
                document_version="v1",
                segment_id="seg_1",
            )
        )

        assert store.delete_document(document.document_id, ALICE) is True

        assert store.get_document(document.document_id, ALICE) is None
        assert store.get_source(document.document_id) is None
        assert store.get_job(job.job_id, ALICE) is None
        assert store.get_job_for_worker(job.job_id) is None
        assert store.get_audio(record.cache_key, ALICE) is None
        assert store.get_progress(document.document_id, ALICE) is None

    def test_another_owner_cannot_delete(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)

        assert store.delete_document(document.document_id, BOB) is False
        assert store.get_document(document.document_id, ALICE) is not None

    def test_deleting_what_is_not_there_is_false(self, store: Store) -> None:
        assert store.delete_document("doc_nothing", ALICE) is False

    def test_only_the_named_document_goes(self, store: Store) -> None:
        keep = a_document(owner=ALICE)
        drop = a_document(owner=ALICE)
        for document in (keep, drop):
            store.put_document(document)
            store.put_source(document.document_id, b"pdf")
            store.put_audio(an_audio_record(document))

        store.delete_document(drop.document_id, ALICE)

        assert store.get_document(keep.document_id, ALICE) is not None
        assert store.get_source(keep.document_id) == b"pdf"
