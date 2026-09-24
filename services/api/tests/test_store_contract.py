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
    AuditEvent,
    Bookmark,
    Classroom,
    CodeTaken,
    Document,
    EmailTaken,
    InMemoryStore,
    Job,
    JobState,
    MemberState,
    PageDecision,
    Progress,
    Publication,
    RightsBasis,
    Role,
    Session,
    Store,
    TeacherInvite,
    User,
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

    def test_the_latest_job_of_each_book_in_one_call(self, store: Store) -> None:
        one, two = a_document(), a_document()
        store.put_document(one)
        store.put_document(two)
        failed = a_job(one, created_at="2026-01-01T00:00:00+00:00", state=JobState.FAILED)
        retried = a_job(one, created_at="2026-02-01T00:00:00+00:00")
        only = a_job(two, created_at="2026-01-15T00:00:00+00:00")
        for job in (retried, only, failed):
            store.put_job(job)

        latest = store.latest_jobs(ALICE)

        assert {d: j.job_id for d, j in latest.items()} == {
            one.document_id: retried.job_id,
            two.document_id: only.job_id,
        }
        assert store.latest_jobs(BOB) == {}


# --- job leases ------------------------------------------------------------

#: Far enough either side of any real clock that the tests do not depend on it.
LONG_AGO = "2000-01-01T00:00:00+00:00"
FAR_AHEAD = "2999-01-01T00:00:00+00:00"


class TestJobLeases:
    """A running job whose process has died must not say "running" for ever.

    One did, for eight days: the process preparing it went away, and a reader
    was told their book was still being prepared the whole time.
    """

    def _running(self, store: Store, lease: str | None) -> Job:
        document = a_document()
        store.put_document(document)
        return store.put_job(a_job(document, state=JobState.RUNNING, lease_expires_at=lease))

    def test_the_lease_survives_a_round_trip(self, store: Store) -> None:
        job = self._running(store, FAR_AHEAD)

        got = store.get_job(job.job_id, ALICE)

        assert got is not None and got.lease_expires_at == FAR_AHEAD

    def test_a_job_past_its_lease_is_failed_as_stalled(self, store: Store) -> None:
        job = self._running(store, LONG_AGO)

        failed = store.fail_stalled_jobs(FAR_AHEAD, LONG_AGO, "it stopped")

        assert failed == [job.job_id]
        got = store.get_job(job.job_id, ALICE)
        assert got is not None
        assert (got.state, got.stage, got.detail) == (JobState.FAILED, "stalled", "it stopped")
        assert got.lease_expires_at is None

    def test_a_job_with_a_live_lease_is_left_running(self, store: Store) -> None:
        job = self._running(store, FAR_AHEAD)

        assert store.fail_stalled_jobs(LONG_AGO, LONG_AGO, "it stopped") == []
        got = store.get_job(job.job_id, ALICE)
        assert got is not None and got.state is JobState.RUNNING

    def test_only_running_jobs_are_reaped(self, store: Store) -> None:
        """A queued or finished job has no process to have died."""
        document = a_document()
        store.put_document(document)
        for state in (JobState.QUEUED, JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
            store.put_job(a_job(document, state=state, lease_expires_at=LONG_AGO))

        assert store.fail_stalled_jobs(FAR_AHEAD, FAR_AHEAD, "it stopped") == []

    def test_reaping_twice_fails_a_job_once(self, store: Store) -> None:
        """Several processes may reap at the same moment."""
        self._running(store, LONG_AGO)

        store.fail_stalled_jobs(FAR_AHEAD, LONG_AGO, "it stopped")

        assert store.fail_stalled_jobs(FAR_AHEAD, LONG_AGO, "it stopped") == []

    def test_a_heartbeat_extends_the_lease(self, store: Store) -> None:
        job = self._running(store, LONG_AGO)

        assert store.renew_lease(job.job_id, FAR_AHEAD) is True
        assert store.fail_stalled_jobs("2500-01-01T00:00:00+00:00", LONG_AGO, "x") == []

    def test_a_heartbeat_after_the_reaper_cannot_revive_the_job(self, store: Store) -> None:
        """Otherwise a failed job could go back to "running" with nothing behind it."""
        job = self._running(store, LONG_AGO)
        store.fail_stalled_jobs(FAR_AHEAD, LONG_AGO, "it stopped")

        assert store.renew_lease(job.job_id, FAR_AHEAD) is False
        got = store.get_job(job.job_id, ALICE)
        assert got is not None and got.state is JobState.FAILED

    def test_a_job_started_before_leases_gets_the_same_grace(self, store: Store) -> None:
        """No lease at all: judged by when it was last updated.

        It is failed only once that is older than the grace period, not the
        moment new code starts, which would fail work still in progress.
        """
        job = self._running(store, None)

        assert store.fail_stalled_jobs(FAR_AHEAD, LONG_AGO, "x") == []
        assert store.fail_stalled_jobs(FAR_AHEAD, FAR_AHEAD, "x") == [job.job_id]

    def test_a_missing_job_has_no_lease_to_renew(self, store: Store) -> None:
        assert store.renew_lease("job_nothing", FAR_AHEAD) is False


# --- job progress ----------------------------------------------------------


class TestJobProgress:
    def _job(self, store: Store, state: JobState) -> Job:
        document = a_document()
        store.put_document(document)
        return store.put_job(a_job(document, state=state))

    def test_a_running_job_records_its_page(self, store: Store) -> None:
        job = self._job(store, JobState.RUNNING)

        assert store.report_progress(job.job_id, "recognising", 12, 168) is True

        got = store.get_job(job.job_id, ALICE)
        assert got is not None
        assert (got.stage, got.pages_done, got.pages_total) == ("recognising", 12, 168)
        assert got.state is JobState.RUNNING

    def test_a_late_report_cannot_move_a_finished_job(self, store: Store) -> None:
        """The worker's report can arrive after the reaper, or after a cancel."""
        for state in (JobState.QUEUED, JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
            job = self._job(store, state)

            assert store.report_progress(job.job_id, "extracting", 1, 2) is False

            got = store.get_job(job.job_id, ALICE)
            assert got is not None
            assert (got.state, got.pages_done) == (state, None)

    def test_progress_survives_a_whole_job_write(self, store: Store) -> None:
        from dataclasses import replace

        job = self._job(store, JobState.RUNNING)
        store.put_job(replace(job, pages_done=3, pages_total=9))

        got = store.get_job(job.job_id, ALICE)
        assert got is not None and (got.pages_done, got.pages_total) == (3, 9)

    def test_a_missing_job_records_nothing(self, store: Store) -> None:
        assert store.report_progress("job_nothing", "extracting", 1, 1) is False


# --- audio -----------------------------------------------------------------


class TestAudio:
    def test_round_trips_byte_for_byte(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        wav = bytes(range(256)) * 100
        record = an_audio_record(document, wav=wav)

        store.put_audio(record)
        got = store.get_audio(record.cache_key, record.document_id, ALICE)

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

        assert store.get_audio(record.cache_key, record.document_id, BOB) is None

    def test_the_real_model_flag_survives(self, store: Store) -> None:
        """It is part of cache identity and of every response.

        A placeholder tone that came back saying it was real would be served as
        narration to a reader who cannot see the screen to check.
        """
        document = a_document()
        store.put_document(document)
        record = an_audio_record(document, is_real_model=True, model_version="ce18fe82442ccbd3")
        store.put_audio(record)

        got = store.get_audio(record.cache_key, record.document_id, ALICE)

        assert got is not None and got.is_real_model is True
        assert got.model_version == "ce18fe82442ccbd3"

    def test_a_missing_key_is_none(self, store: Store) -> None:
        assert store.get_audio("key_nothing", "doc_nothing", ALICE) is None

    def test_two_readers_of_the_same_book_each_keep_their_audio(self, store: Store) -> None:
        """The key comes from the text, not the reader, so it is shared.

        Two readers who upload the same PDF produce the same key for the same
        sentence. When audio was keyed on that alone, Postgres kept the first
        reader's clip and silently dropped the second's, and the in-memory store
        let each overwrite the other. Either way one of them was synthesising
        the same sentence again on every play.
        """
        alices, bobs = a_document(owner=ALICE), a_document(owner=BOB)
        store.put_document(alices)
        store.put_document(bobs)
        key = "key_same_sentence_same_settings"

        store.put_audio(an_audio_record(alices, cache_key=key, wav=b"alice"))
        store.put_audio(an_audio_record(bobs, cache_key=key, wav=b"bob"))

        alice_got = store.get_audio(key, alices.document_id, ALICE)
        bob_got = store.get_audio(key, bobs.document_id, BOB)
        assert alice_got is not None and alice_got.wav == b"alice"
        assert bob_got is not None and bob_got.wav == b"bob"

    def test_deleting_one_readers_book_keeps_the_others_audio(self, store: Store) -> None:
        alices, bobs = a_document(owner=ALICE), a_document(owner=BOB)
        store.put_document(alices)
        store.put_document(bobs)
        key = "key_same_sentence_same_settings"
        store.put_audio(an_audio_record(alices, cache_key=key, wav=b"alice"))
        store.put_audio(an_audio_record(bobs, cache_key=key, wav=b"bob"))

        store.delete_document(alices.document_id, ALICE)

        assert store.get_audio(key, alices.document_id, ALICE) is None
        bob_got = store.get_audio(key, bobs.document_id, BOB)
        assert bob_got is not None and bob_got.wav == b"bob"


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


# --- bookmarks -------------------------------------------------------------


def a_bookmark(document: Document, segment_id: str = "seg_1", **kwargs: object) -> Bookmark:
    fields: dict[str, object] = {
        "bookmark_id": new_id("bmk"),
        "document_id": document.document_id,
        "owner": document.owner,
        "document_version": "v1",
        "segment_id": segment_id,
    }
    fields.update(kwargs)
    return Bookmark(**fields)  # type: ignore[arg-type]


class TestBookmarks:
    def test_round_trips(self, store: Store) -> None:
        document = a_document(version="v1")
        store.put_document(document)
        bookmark = a_bookmark(document, note="where the chapter turns")

        stored, created = store.put_bookmark(bookmark)

        assert created is True
        assert stored == bookmark
        assert store.get_bookmark(bookmark.bookmark_id, ALICE) == bookmark

    def test_a_bookmark_with_no_note_is_still_a_bookmark(self, store: Store) -> None:
        """Most will have none. Marking a place is the whole feature."""
        document = a_document()
        store.put_document(document)

        stored, _ = store.put_bookmark(a_bookmark(document))

        assert stored.note is None

    def test_a_second_bookmark_on_one_segment_replaces_the_first(self, store: Store) -> None:
        """The control is a button pressed without seeing what it did.

        A double press must not leave two identical entries that then have to
        be found and deleted twice by someone navigating a list by ear.
        """
        document = a_document()
        store.put_document(document)
        first, _ = store.put_bookmark(a_bookmark(document, segment_id="seg_4", note="here"))

        again, created = store.put_bookmark(
            a_bookmark(document, segment_id="seg_4", note="here, really")
        )

        assert created is False
        # The reader's edit is kept; the bookmark's identity and age are not
        # replaced, so editing a note does not move it in an ordered list.
        assert again.note == "here, really"
        assert again.bookmark_id == first.bookmark_id
        assert again.created_at == first.created_at
        assert len(store.list_bookmarks(document.document_id, ALICE)) == 1

    def test_two_readers_can_bookmark_the_same_segment(self, store: Store) -> None:
        """One bookmark per segment is per reader, not per sentence."""
        mine = a_document(owner=ALICE)
        theirs = a_document(owner=BOB)
        store.put_document(mine)
        store.put_document(theirs)

        store.put_bookmark(a_bookmark(mine, segment_id="seg_4"))
        _, created = store.put_bookmark(a_bookmark(theirs, segment_id="seg_4"))

        assert created is True

    def test_listing_is_scoped_and_oldest_first(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)
        later = a_bookmark(document, segment_id="seg_9", created_at="2026-06-01T00:00:00+00:00")
        earlier = a_bookmark(document, segment_id="seg_2", created_at="2026-01-01T00:00:00+00:00")
        store.put_bookmark(later)
        store.put_bookmark(earlier)

        listed = store.list_bookmarks(document.document_id, ALICE)

        assert [b.segment_id for b in listed] == ["seg_2", "seg_9"]
        assert store.list_bookmarks(document.document_id, BOB) == []

    def test_listing_is_scoped_to_one_document(self, store: Store) -> None:
        one = a_document(owner=ALICE)
        two = a_document(owner=ALICE)
        store.put_document(one)
        store.put_document(two)
        store.put_bookmark(a_bookmark(one))
        store.put_bookmark(a_bookmark(two))

        assert len(store.list_bookmarks(one.document_id, ALICE)) == 1

    def test_another_reader_can_neither_see_nor_delete_one(self, store: Store) -> None:
        document = a_document(owner=ALICE)
        store.put_document(document)
        bookmark, _ = store.put_bookmark(a_bookmark(document))

        assert store.get_bookmark(bookmark.bookmark_id, BOB) is None
        assert store.delete_bookmark(bookmark.bookmark_id, BOB) is False
        assert store.get_bookmark(bookmark.bookmark_id, ALICE) is not None

    def test_deleting_one_leaves_the_others(self, store: Store) -> None:
        document = a_document()
        store.put_document(document)
        keep, _ = store.put_bookmark(a_bookmark(document, segment_id="seg_1"))
        drop, _ = store.put_bookmark(a_bookmark(document, segment_id="seg_2"))

        assert store.delete_bookmark(drop.bookmark_id, ALICE) is True

        assert [b.bookmark_id for b in store.list_bookmarks(document.document_id, ALICE)] == [
            keep.bookmark_id
        ]

    def test_deleting_what_is_not_there_is_false(self, store: Store) -> None:
        assert store.delete_bookmark("bmk_nothing", ALICE) is False

    def test_the_segment_is_free_again_after_a_delete(self, store: Store) -> None:
        """Otherwise a reader who removes a bookmark cannot make a new one."""
        document = a_document()
        store.put_document(document)
        bookmark, _ = store.put_bookmark(a_bookmark(document, segment_id="seg_4"))
        store.delete_bookmark(bookmark.bookmark_id, ALICE)

        _, created = store.put_bookmark(a_bookmark(document, segment_id="seg_4"))

        assert created is True


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
        bookmark, _ = store.put_bookmark(a_bookmark(document))
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
        assert store.get_audio(record.cache_key, record.document_id, ALICE) is None
        assert store.get_progress(document.document_id, ALICE) is None
        assert store.get_bookmark(bookmark.bookmark_id, ALICE) is None
        assert store.list_bookmarks(document.document_id, ALICE) == []

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


# --- accounts --------------------------------------------------------------


def a_user(email: str = "nimali@example.lk", **kwargs: object) -> User:
    fields: dict[str, object] = {
        "user_id": new_id("usr"),
        "email": email,
        "email_key": email.lower(),
        "password_hash": "scrypt$14$8$5$c2FsdA$a2V5",
        "display_name": "Nimali",
    }
    fields.update(kwargs)
    return User(**fields)  # type: ignore[arg-type]


class TestUsers:
    def test_round_trips_by_id_and_by_email(self, store: Store) -> None:
        user = a_user()
        store.put_user(user)

        assert store.get_user(user.user_id) == user
        assert store.get_user_by_email("nimali@example.lk") == user

    def test_lookup_is_by_the_lowercased_key(self, store: Store) -> None:
        """A reader who typed capitals when registering must still be able to sign in."""
        store.put_user(a_user(email="Nimali@Example.LK", email_key="nimali@example.lk"))

        assert store.get_user_by_email("nimali@example.lk") is not None
        # And the address they typed is kept as they typed it.
        found = store.get_user_by_email("nimali@example.lk")
        assert found is not None and found.email == "Nimali@Example.LK"

    def test_a_second_account_cannot_take_the_address(self, store: Store) -> None:
        """Enforced by the store, not by a check in a route.

        A check followed by an insert leaves a gap that two simultaneous
        registrations both pass through.
        """
        store.put_user(a_user())

        with pytest.raises(EmailTaken):
            store.put_user(a_user())

    def test_the_same_user_may_be_written_again(self, store: Store) -> None:
        """A password change rewrites the row; that is not a clash."""
        user = a_user()
        store.put_user(user)

        from dataclasses import replace

        store.put_user(replace(user, password_hash="scrypt$14$8$5$bmV3$aGFzaA"))

        got = store.get_user(user.user_id)
        assert got is not None and got.password_hash == "scrypt$14$8$5$bmV3$aGFzaA"

    def test_absent_is_none(self, store: Store) -> None:
        assert store.get_user("usr_nothing") is None
        assert store.get_user_by_email("nobody@example.lk") is None


class TestSessions:
    def test_round_trips(self, store: Store) -> None:
        user = a_user()
        store.put_user(user)
        session = Session(
            token_hash="abc123",
            user_id=user.user_id,
            created_at="2026-09-10T00:00:00+00:00",
            expires_at="2026-09-24T00:00:00+00:00",
        )

        store.put_session(session)

        assert store.get_session("abc123") == session

    def test_expiry_is_not_judged_here(self, store: Store) -> None:
        """The store returns what it holds; deciding it is dead belongs in one place.

        If each store filtered by expiry, "expired" and "never existed" could
        drift apart between implementations.
        """
        user = a_user()
        store.put_user(user)
        store.put_session(
            Session(
                token_hash="expired",
                user_id=user.user_id,
                created_at="2020-01-01T00:00:00+00:00",
                expires_at="2020-01-02T00:00:00+00:00",
            )
        )

        assert store.get_session("expired") is not None

    def test_deleting_one_session(self, store: Store) -> None:
        user = a_user()
        store.put_user(user)
        store.put_session(
            Session(
                token_hash="one",
                user_id=user.user_id,
                created_at="2026-09-10T00:00:00+00:00",
                expires_at="2026-09-24T00:00:00+00:00",
            )
        )

        assert store.delete_session("one") is True
        assert store.get_session("one") is None
        assert store.delete_session("one") is False

    def test_ending_every_session_a_reader_has(self, store: Store) -> None:
        """What a password change relies on.

        A password changed because someone else may know it has not been
        changed at all if their session keeps working.
        """
        nimali = a_user(email="nimali@example.lk")
        sahan = a_user(email="sahan@example.lk")
        store.put_user(nimali)
        store.put_user(sahan)
        for index, user in ((1, nimali), (2, nimali), (3, sahan)):
            store.put_session(
                Session(
                    token_hash=f"token-{index}",
                    user_id=user.user_id,
                    created_at="2026-09-10T00:00:00+00:00",
                    expires_at="2026-09-24T00:00:00+00:00",
                )
            )

        assert store.delete_sessions_for_user(nimali.user_id) == 2
        assert store.get_session("token-1") is None
        assert store.get_session("token-2") is None
        # The other reader is untouched.
        assert store.get_session("token-3") is not None

    def test_an_unknown_token_is_none(self, store: Store) -> None:
        assert store.get_session("never-issued") is None


# --- roles, invitations and the audit log ----------------------------------


class TestRoles:
    def test_a_new_account_is_a_student(self, store: Store) -> None:
        user = store.put_user(a_user())
        got = store.get_user(user.user_id)
        assert got is not None and got.role is Role.STUDENT

    def test_set_role_is_the_way_a_role_changes(self, store: Store) -> None:
        user = store.put_user(a_user())

        assert store.set_role(user.user_id, Role.TEACHER) is True

        got = store.get_user(user.user_id)
        assert got is not None and got.role is Role.TEACHER

    def test_a_whole_user_write_keeps_the_role_and_recovery_code(self, store: Store) -> None:
        """A stale copy written back must not demote a teacher or revive a code."""
        from dataclasses import replace

        user = store.put_user(a_user())
        store.set_role(user.user_id, Role.TEACHER)

        store.put_user(replace(user, display_name="Renamed", recovery_hash="stale"))

        got = store.get_user(user.user_id)
        assert got is not None
        assert (got.display_name, got.role, got.recovery_hash) == ("Renamed", Role.TEACHER, None)

    def test_a_missing_account_has_no_role_to_set(self, store: Store) -> None:
        assert store.set_role("usr_nobody", Role.ADMIN) is False

    def test_a_recovery_code_is_set_and_cleared_by_its_own_method(self, store: Store) -> None:
        user = store.put_user(a_user())

        assert store.set_recovery_hash(user.user_id, "hash-one") is True
        got = store.get_user(user.user_id)
        assert got is not None and got.recovery_hash == "hash-one"

        store.set_recovery_hash(user.user_id, None)
        got = store.get_user(user.user_id)
        assert got is not None and got.recovery_hash is None
        assert store.set_recovery_hash("usr_nobody", "x") is False


class TestDeletingAUser:
    def test_takes_its_sessions_and_history_with_it(self, store: Store) -> None:
        user = store.put_user(a_user())
        store.put_session(
            Session(
                token_hash="h1",
                user_id=user.user_id,
                created_at="2026-09-01T00:00:00+00:00",
                expires_at="2099-01-01T00:00:00+00:00",
            )
        )
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="role_granted",
                actor="cli",
                subject=user.user_id,
                reason="student->teacher:school-staff",
            )
        )

        assert store.delete_user(user.user_id) is True

        assert store.get_user(user.user_id) is None
        assert store.get_user_by_email(user.email_key) is None
        assert store.get_session("h1") is None
        assert store.audit_for(user.user_id) == []

    def test_a_spent_invitation_stays_spent(self, store: Store) -> None:
        user = store.put_user(a_user())
        store.put_invite(
            TeacherInvite(
                code_hash="c1",
                created_by="cli",
                created_at="2026-09-01T00:00:00+00:00",
                expires_at="2099-01-01T00:00:00+00:00",
            )
        )
        store.redeem_invite("c1", user.user_id, "2026-09-02T00:00:00+00:00")

        store.delete_user(user.user_id)

        other = store.put_user(a_user("other@example.lk"))
        assert store.redeem_invite("c1", other.user_id, "2026-09-03T00:00:00+00:00") is False

    def test_a_missing_user_is_nothing_to_delete(self, store: Store) -> None:
        assert store.delete_user("usr_nobody") is False


class TestTeacherInvites:
    NOW = "2026-09-01T00:00:00+00:00"

    def _invite(self, store: Store, expires_at: str = "2026-09-08T00:00:00+00:00") -> str:
        code_hash = new_id("hash")
        store.put_invite(
            TeacherInvite(
                code_hash=code_hash,
                created_by="cli",
                created_at="2026-08-31T00:00:00+00:00",
                expires_at=expires_at,
            )
        )
        return code_hash

    def test_redeems_once(self, store: Store) -> None:
        one = store.put_user(a_user("one@example.lk"))
        two = store.put_user(a_user("two@example.lk"))
        code_hash = self._invite(store)

        assert store.redeem_invite(code_hash, one.user_id, self.NOW) is True
        assert store.redeem_invite(code_hash, two.user_id, self.NOW) is False

    def test_an_expired_one_is_not_redeemed(self, store: Store) -> None:
        user = store.put_user(a_user())
        code_hash = self._invite(store, expires_at="2026-08-31T12:00:00+00:00")

        assert store.redeem_invite(code_hash, user.user_id, self.NOW) is False

    def test_an_unknown_one_is_not_redeemed(self, store: Store) -> None:
        user = store.put_user(a_user())
        assert store.redeem_invite("never-issued", user.user_id, self.NOW) is False


class TestAudit:
    def test_records_are_read_back_per_account_oldest_first(self, store: Store) -> None:
        user = store.put_user(a_user())
        other = store.put_user(a_user("other@example.lk"))
        later = AuditEvent(
            event_id=new_id("aud"),
            kind="role_granted",
            actor="cli",
            subject=user.user_id,
            reason="teacher->student:revoked",
            at="2026-09-02T00:00:00+00:00",
        )
        earlier = AuditEvent(
            event_id=new_id("aud"),
            kind="role_granted",
            actor="cli",
            subject=user.user_id,
            reason="student->teacher:verified-teacher",
            at="2026-09-01T00:00:00+00:00",
        )
        for event in (later, earlier):
            store.record(event)
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="role_granted",
                actor="cli",
                subject=other.user_id,
                reason="student->teacher:school-staff",
            )
        )

        assert store.audit_for(user.user_id) == [earlier, later]

    def test_an_event_about_no_account_is_kept(self, store: Store) -> None:
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="invite_created",
                actor="cli",
                subject=None,
                reason="teacher:7d",
            )
        )


# --- classes -----------------------------------------------------------------


class TestClasses:
    def _setup(self, store: Store) -> tuple[User, User, Classroom]:
        teacher = store.put_user(a_user("teacher@school.lk"))
        student = store.put_user(a_user("student@school.lk"))
        room = store.put_class(
            Classroom(
                class_id=new_id("cls"), teacher_id=teacher.user_id, name="10", join_code="12345678"
            )
        )
        return teacher, student, room

    def test_a_class_is_its_teachers_and_found_by_code(self, store: Store) -> None:
        teacher, student, room = self._setup(store)

        assert store.class_taught(room.class_id, teacher.user_id) == room
        assert store.class_taught(room.class_id, student.user_id) is None
        assert store.classes_taught(teacher.user_id) == [room]
        assert store.class_by_code("12345678") == room
        assert store.class_by_code("87654321") is None

    def test_two_classes_cannot_share_a_code(self, store: Store) -> None:
        teacher, _, _ = self._setup(store)
        with pytest.raises(CodeTaken):
            store.put_class(
                Classroom(
                    class_id=new_id("cls"),
                    teacher_id=teacher.user_id,
                    name="11",
                    join_code="12345678",
                )
            )

    def test_joining_is_pending_until_the_teacher_approves(self, store: Store) -> None:
        teacher, student, room = self._setup(store)

        joined = store.join_class(room.class_id, student.user_id)
        assert joined.state is MemberState.PENDING
        assert store.set_member_state(
            room.class_id, teacher.user_id, student.user_id, MemberState.ACTIVE
        )
        assert store.membership(room.class_id, student.user_id).state is MemberState.ACTIVE
        # Joining again leaves an active member as they were.
        assert store.join_class(room.class_id, student.user_id).state is MemberState.ACTIVE

    def test_only_the_teacher_can_change_a_member(self, store: Store) -> None:
        _, student, room = self._setup(store)
        store.join_class(room.class_id, student.user_id)

        assert not store.set_member_state(
            room.class_id, student.user_id, student.user_id, MemberState.ACTIVE
        )
        assert store.members(room.class_id, student.user_id) == []
        assert store.membership(room.class_id, student.user_id).state is MemberState.PENDING

    def test_a_removed_member_is_gone_from_their_list_and_rejoins_as_pending(
        self, store: Store
    ) -> None:
        teacher, student, room = self._setup(store)
        store.join_class(room.class_id, student.user_id)
        store.set_share_progress(room.class_id, student.user_id, True)
        store.set_member_state(room.class_id, teacher.user_id, student.user_id, MemberState.REMOVED)

        assert store.classes_joined(student.user_id) == []
        again = store.join_class(room.class_id, student.user_id)
        assert (again.state, again.share_progress) == (MemberState.PENDING, False)

    def test_sharing_progress_is_the_members_to_set(self, store: Store) -> None:
        _, student, room = self._setup(store)
        store.join_class(room.class_id, student.user_id)

        assert store.set_share_progress(room.class_id, student.user_id, True)
        on = store.membership(room.class_id, student.user_id)
        assert on.share_progress and on.consented_at is not None
        store.set_share_progress(room.class_id, student.user_id, False)
        off = store.membership(room.class_id, student.user_id)
        assert (off.share_progress, off.consented_at) == (False, None)

    def test_leaving_and_deleting_take_the_membership(self, store: Store) -> None:
        teacher, student, room = self._setup(store)
        store.join_class(room.class_id, student.user_id)

        assert store.leave_class(room.class_id, student.user_id)
        assert store.membership(room.class_id, student.user_id) is None
        store.join_class(room.class_id, student.user_id)
        assert not store.delete_class(room.class_id, student.user_id)
        assert store.delete_class(room.class_id, teacher.user_id)
        assert store.membership(room.class_id, student.user_id) is None

    def test_a_new_code_replaces_the_old(self, store: Store) -> None:
        teacher, student, room = self._setup(store)

        assert not store.set_join_code(room.class_id, student.user_id, "11112222")
        assert store.set_join_code(room.class_id, teacher.user_id, "11112222")
        assert store.class_by_code("12345678") is None
        assert store.class_by_code("11112222").class_id == room.class_id

    def test_deleting_a_teacher_takes_their_classes(self, store: Store) -> None:
        teacher, student, room = self._setup(store)
        store.join_class(room.class_id, student.user_id)

        store.delete_user(teacher.user_id)

        assert store.class_by_code("12345678") is None
        assert store.membership(room.class_id, student.user_id) is None


# --- publishing ----------------------------------------------------------------

PAYLOAD = '{"payload": true}'


class TestPublishing:
    """The reading predicate: the owner, or an active member of a class the
    book is shared with, at the shared version, without withheld pages."""

    def _world(self, store: Store):
        teacher = store.put_user(a_user("teacher@school.lk"))
        student = store.put_user(a_user("student@school.lk"))
        stranger = store.put_user(a_user("stranger@example.lk"))
        room = store.put_class(
            Classroom(
                class_id=new_id("cls"), teacher_id=teacher.user_id, name="A", join_code="12345678"
            )
        )
        store.join_class(room.class_id, student.user_id)
        store.set_member_state(room.class_id, teacher.user_id, student.user_id, MemberState.ACTIVE)
        document = store.put_document(a_document(owner=teacher.user_id, version="v1"))
        return teacher, student, stranger, room, document

    def _publish(self, store: Store, teacher, document, room, version: str = "v1") -> bool:
        return store.publish(
            Publication(
                document_id=document.document_id,
                teacher_id=teacher.user_id,
                version=version,
                basis=RightsBasis.OWN_WORK,
            ),
            [room.class_id],
            PAYLOAD,
        )

    def test_the_owner_reads_their_book_as_it_stands(self, store: Store) -> None:
        teacher, _, _, _, document = self._world(store)

        reading = store.readable_document(document.document_id, teacher.user_id)

        assert reading is not None and reading.as_owner
        assert reading.document.version == "v1"

    def test_nobody_else_reads_an_unshared_book(self, store: Store) -> None:
        _, student, stranger, _, document = self._world(store)

        assert store.readable_document(document.document_id, student.user_id) is None
        assert store.readable_document(document.document_id, stranger.user_id) is None

    def test_an_active_member_reads_the_pinned_version(self, store: Store) -> None:
        from dataclasses import replace

        teacher, student, stranger, room, document = self._world(store)
        assert self._publish(store, teacher, document, room)
        store.put_document(replace(document, version="v2"))  # the owner moves on

        reading = store.readable_document(document.document_id, student.user_id)

        assert reading is not None and not reading.as_owner
        assert reading.document.version == "v1"
        assert store.get_prepared_version(document.document_id, "v1") == PAYLOAD
        assert store.readable_document(document.document_id, stranger.user_id) is None

    def test_a_pending_or_removed_member_reads_nothing(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        self._publish(store, teacher, document, room)

        for state in (MemberState.PENDING, MemberState.REMOVED):
            store.set_member_state(room.class_id, teacher.user_id, student.user_id, state)
            assert store.readable_document(document.document_id, student.user_id) is None

    def test_withheld_pages_travel_with_the_reading(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        doc = document.document_id
        store.put_page_review(doc, teacher.user_id, "v1", 3, PageDecision.WITHHELD)
        store.put_page_review(doc, teacher.user_id, "v1", 4, PageDecision.ACCEPTED)
        self._publish(store, teacher, document, room)

        reading = store.readable_document(doc, student.user_id)

        assert reading is not None and reading.withheld == frozenset({3})
        assert store.page_reviews(doc, teacher.user_id, "v1") == {
            3: PageDecision.WITHHELD,
            4: PageDecision.ACCEPTED,
        }
        # Only the owner records or reads decisions.
        assert not store.put_page_review(doc, student.user_id, "v1", 3, PageDecision.ACCEPTED)
        assert store.page_reviews(doc, student.user_id, "v1") == {}

    def test_publishing_is_all_or_nothing(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        other = store.put_user(a_user("other@school.lk"))
        theirs = store.put_class(
            Classroom(
                class_id=new_id("cls"), teacher_id=other.user_id, name="B", join_code="87654321"
            )
        )

        shared = store.publish(
            Publication(
                document_id=document.document_id,
                teacher_id=teacher.user_id,
                version="v1",
                basis=RightsBasis.OWN_WORK,
            ),
            [room.class_id, theirs.class_id],
            "{}",
        )

        assert not shared
        assert store.publication(document.document_id, teacher.user_id) is None
        assert store.readable_document(document.document_id, student.user_id) is None

    def test_only_the_owner_publishes_their_own_book(self, store: Store) -> None:
        teacher, student, _, room, _ = self._world(store)
        mine = store.put_document(a_document(owner=student.user_id, version="v1"))

        assert not self._publish(store, teacher, mine, room)

    def test_the_owner_sees_where_it_is_shared(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        self._publish(store, teacher, document, room)

        found = store.publication(document.document_id, teacher.user_id)

        assert found is not None
        publication, classes = found
        assert (publication.version, publication.basis, classes) == (
            "v1",
            RightsBasis.OWN_WORK,
            [room.class_id],
        )
        assert store.publication(document.document_id, student.user_id) is None

    def test_class_books_lists_what_a_member_may_read(self, store: Store) -> None:
        teacher, student, stranger, room, document = self._world(store)
        self._publish(store, teacher, document, room)

        (listed,) = store.class_books(student.user_id)

        assert listed[0].class_id == room.class_id
        assert listed[1].document_id == document.document_id and listed[1].version == "v1"
        assert store.class_books(stranger.user_id) == []
        assert store.class_books(teacher.user_id) == []

    def test_unpublishing_ends_access_and_is_the_owners_to_do(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        self._publish(store, teacher, document, room)

        assert not store.unpublish(document.document_id, student.user_id, room.class_id)
        assert store.unpublish(document.document_id, teacher.user_id, room.class_id)
        assert store.readable_document(document.document_id, student.user_id) is None
        assert store.class_books(student.user_id) == []

    def test_deleting_the_book_or_the_class_takes_the_sharing(self, store: Store) -> None:
        teacher, student, _, room, document = self._world(store)
        self._publish(store, teacher, document, room)

        store.delete_document(document.document_id, teacher.user_id)

        assert store.class_books(student.user_id) == []
        assert store.get_prepared_version(document.document_id, "v1") is None

        again = store.put_document(a_document(owner=teacher.user_id, version="v1"))
        self._publish(store, teacher, again, room)
        store.delete_class(room.class_id, teacher.user_id)
        assert store.readable_document(again.document_id, student.user_id) is None
