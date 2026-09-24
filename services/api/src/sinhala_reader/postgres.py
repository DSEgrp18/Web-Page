"""The ``Store`` interface, on PostgreSQL.

This is the first of the three stopgaps in ``services/api/README.md`` to be
replaced. ``InMemoryStore`` loses every document, every generated clip and every
reading position when the process stops; a reader who was halfway through a
chapter came back to nothing, and a 168-page book had to be extracted again from
the beginning.

Three decisions here are load-bearing, and each is a property the interface
promises rather than a database preference.

**Ownership is a ``WHERE`` clause, never an application check.** Every read that
takes an owner puts it in the statement, so a forgotten check is a syntax error
rather than a silent leak. Another reader's document comes back as no rows,
which the API turns into a 404 — a 403 on an id that exists confirms it exists,
and these are private books belonging to identifiable students.

**Deletion is the database's job, through ``ON DELETE CASCADE``.** CLAUDE.md
requires deletion to remove derived text, audio and caches, and an application
that deletes five tables in sequence can be interrupted between two of them.
Cascading makes "everything derived" a property of the schema: a new table that
references a document is cleaned up because it references a document, not
because somebody remembered to add it to a delete method.

**Timestamps are stored as text, not ``timestamptz``.** The interface promises
ISO-8601 strings and the tests compare them exactly; a round trip through
``timestamptz`` normalises the format and the equality fails. The cost is that
no date arithmetic can happen in SQL — nothing needs it, and ordering still
works because these strings are all UTC and sort lexicographically in the same
order the in-memory store sorts them. If a query ever needs real date
arithmetic, that is the moment to add a proper column beside this one rather
than to change what the interface returns.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .storage import (
    AudioRecord,
    AuditEvent,
    Bookmark,
    Classroom,
    CodeTaken,
    Document,
    EmailTaken,
    Job,
    JobState,
    Membership,
    MemberState,
    PageDecision,
    Progress,
    Publication,
    Reading,
    RightsBasis,
    Role,
    Session,
    Store,
    TeacherInvite,
    TeacherReset,
    User,
    _now,
)

#: Where the database is. Unset means the in-memory store, which is the safe
#: default: a test run and a `--reload` must not need a server.
DATABASE_URL_ENV = "SINHALA_READER_DATABASE_URL"


# --- schema ----------------------------------------------------------------

#: Applied in order, each exactly once, recorded in ``schema_migrations``.
#:
#: CLAUDE.md asks for explicit, backward-compatible migrations. Numbered SQL is
#: the smallest thing that is both: it is reviewable in a pull request, it runs
#: the same way everywhere, and it does not put a migration framework between a
#: reader of this file and what will actually happen to the database.
#:
#: **Never edit a migration that has been applied anywhere.** Add another.
MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "0001_initial",
        """
        CREATE TABLE documents (
            document_id   text PRIMARY KEY,
            owner         text   NOT NULL,
            filename      text   NOT NULL,
            size_bytes    bigint NOT NULL,
            created_at    text   NOT NULL,
            version       text,
            page_count    integer NOT NULL DEFAULT 0,
            segment_count integer NOT NULL DEFAULT 0,
            notes         text[]  NOT NULL DEFAULT '{}'
        );

        -- The library screen asks for one reader's documents, newest first.
        CREATE INDEX documents_by_owner ON documents (owner, created_at DESC);

        CREATE TABLE sources (
            document_id text PRIMARY KEY
                REFERENCES documents (document_id) ON DELETE CASCADE,
            data        bytea NOT NULL
        );

        CREATE TABLE jobs (
            job_id      text PRIMARY KEY,
            document_id text NOT NULL
                REFERENCES documents (document_id) ON DELETE CASCADE,
            owner       text NOT NULL,
            kind        text NOT NULL,
            state       text NOT NULL,
            stage       text NOT NULL,
            detail      text,
            created_at  text NOT NULL,
            updated_at  text NOT NULL
        );

        CREATE INDEX jobs_by_document ON jobs (document_id, created_at);

        CREATE TABLE audio (
            cache_key        text PRIMARY KEY,
            document_id      text NOT NULL
                REFERENCES documents (document_id) ON DELETE CASCADE,
            owner            text NOT NULL,
            segment_id       text NOT NULL,
            wav              bytea NOT NULL,
            duration_seconds double precision NOT NULL,
            is_real_model    boolean NOT NULL,
            voice_id         text NOT NULL,
            model_version    text NOT NULL
        );

        -- One position per reader per document: a reader has one place they
        -- got to, and writing a second row would make "where was I" ambiguous.
        CREATE TABLE progress (
            document_id      text NOT NULL
                REFERENCES documents (document_id) ON DELETE CASCADE,
            owner            text NOT NULL,
            document_version text NOT NULL,
            segment_id       text NOT NULL,
            offset_seconds   double precision NOT NULL,
            updated_at       text NOT NULL,
            PRIMARY KEY (document_id, owner)
        );
        """,
    ),
    (
        "0002_accounts",
        """
        CREATE TABLE users (
            user_id       text PRIMARY KEY,
            email         text NOT NULL,
            -- Uniqueness is on the lowercased address, enforced by the database
            -- rather than by a check-then-insert in a route: two simultaneous
            -- registrations would both pass the check.
            email_key     text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            display_name  text NOT NULL,
            created_at    text NOT NULL
        );

        CREATE TABLE sessions (
            -- The hash of the token, never the token. A leaked database must
            -- not hand over working sessions.
            token_hash text PRIMARY KEY,
            user_id    text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
            created_at text NOT NULL,
            expires_at text NOT NULL
        );

        -- Ending every session a reader has, for a password change.
        CREATE INDEX sessions_by_user ON sessions (user_id);
        """,
    ),
    (
        "0003_prepared_documents",
        """
        -- The extracted pages and segments, as JSON. Derived data, but about
        -- 30 seconds of work for a 168-page book, and without it a restart
        -- leaves the document row saying "ready" while every page says it is
        -- not. Cascades with the document like everything else derived.
        CREATE TABLE prepared (
            document_id text PRIMARY KEY
                REFERENCES documents (document_id) ON DELETE CASCADE,
            payload     text NOT NULL
        );
        """,
    ),
    (
        "0004_bookmarks",
        """
        CREATE TABLE bookmarks (
            bookmark_id      text PRIMARY KEY,
            document_id      text NOT NULL
                REFERENCES documents (document_id) ON DELETE CASCADE,
            owner            text NOT NULL,
            document_version text NOT NULL,
            segment_id       text NOT NULL,
            -- The reader's own words. No copy of the sentence they marked:
            -- that is read back out of the prepared document, so a bookmark
            -- cannot drift out of step with the book, and deleting a document
            -- does not leave passages of it behind here.
            note             text,
            created_at       text NOT NULL,
            -- One bookmark per segment per reader, enforced here rather than
            -- by a check-then-insert: the control is a button pressed without
            -- seeing what it did, and two presses must not make two entries.
            UNIQUE (owner, document_id, segment_id)
        );

        -- The bookmark list for one reader in one book.
        CREATE INDEX bookmarks_by_document ON bookmarks (document_id, owner, created_at);
        """,
    ),
    (
        "0005_titles_and_reading_position",
        """
        -- What the reader calls the book, when they have said. NULL means they
        -- have not, and the filename stands in. Adding a column rather than
        -- rewriting `filename` keeps what was actually uploaded: a rename is
        -- the reader's label, not a correction of the file.
        ALTER TABLE documents ADD COLUMN title text;

        -- How far into the book the saved position is. Resolved when the
        -- position is written, because the alternative is loading the whole
        -- prepared document on every library render to answer "37%".
        --
        -- Backward-compatible by default: rows written before this migration
        -- report 0, which reads as "at the beginning" rather than as an error.
        ALTER TABLE progress ADD COLUMN segment_index integer NOT NULL DEFAULT 0;
        """,
    ),
    (
        "0006_document_scoped_audio",
        """
        -- A cache key is derived from the text and its settings, not from the
        -- reader, so two readers who upload the same PDF produce the same key
        -- for the same sentence. Keyed on that alone, the second reader's clip
        -- was dropped by ON CONFLICT DO NOTHING and synthesised again on every
        -- play - and once the first reader deleted their copy, the second had
        -- no audio at all.
        --
        -- Each document keeps its own. Existing keys are already unique, so
        -- every existing row satisfies the new key and none is touched.
        ALTER TABLE audio DROP CONSTRAINT audio_pkey;
        ALTER TABLE audio ADD PRIMARY KEY (document_id, cache_key);
        """,
    ),
    (
        "0007_job_leases",
        """
        -- Until when a running job's process has promised it is still alive.
        -- Renewed by a heartbeat; a process that dies stops renewing, and the
        -- job is then failed as stalled instead of saying "running" for ever.
        -- NULL for jobs that are not running, and for any started before this.
        ALTER TABLE jobs ADD COLUMN lease_expires_at text;

        -- The reaper only ever looks at running jobs, which are few.
        CREATE INDEX jobs_running ON jobs (lease_expires_at) WHERE state = 'running';
        """,
    ),
    (
        "0008_job_progress",
        """
        -- How far through its current stage a job is, in pages: "page 12 of
        -- 168". NULL until a stage finishes its first page, and for every job
        -- from before this.
        ALTER TABLE jobs ADD COLUMN pages_done integer;
        ALTER TABLE jobs ADD COLUMN pages_total integer;
        """,
    ),
    (
        "0009_roles_recovery_audit",
        """
        -- Registration always makes a student. A teacher is made by an admin,
        -- on the command line or through an invitation; nobody can declare it.
        ALTER TABLE users ADD COLUMN role text NOT NULL DEFAULT 'student'
            CHECK (role IN ('student', 'teacher', 'admin'));

        -- The hash of the account's one recovery code. NULL for accounts
        -- made before recovery codes, until they make one.
        ALTER TABLE users ADD COLUMN recovery_hash text;

        CREATE TABLE teacher_invites (
            -- The hash of the code, never the code: it is shown once.
            code_hash  text PRIMARY KEY,
            created_by text NOT NULL,
            created_at text NOT NULL,
            expires_at text NOT NULL,
            used_by    text REFERENCES users (user_id) ON DELETE SET NULL,
            used_at    text
        );

        -- What changed what an account may do, and who did it. Codes, never
        -- content. Deleted with the account it is about.
        CREATE TABLE audit_events (
            event_id text PRIMARY KEY,
            kind     text NOT NULL,
            actor    text NOT NULL,
            subject  text REFERENCES users (user_id) ON DELETE CASCADE,
            reason   text NOT NULL,
            at       text NOT NULL
        );
        CREATE INDEX audit_by_subject ON audit_events (subject, at);
        """,
    ),
    (
        "0010_classes",
        """
        -- A teacher's class. The join code is eight digits, easiest on a phone
        -- keypad and with a screen reader, and can be replaced by the teacher.
        CREATE TABLE classes (
            class_id   text PRIMARY KEY,
            teacher_id text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
            name       text NOT NULL,
            join_code  text NOT NULL UNIQUE,
            created_at text NOT NULL
        );
        CREATE INDEX classes_by_teacher ON classes (teacher_id);

        -- One student in one class. Joining makes it pending; the teacher's
        -- approval, not the code, is what lets them in. Progress sharing is
        -- off unless the student turns it on.
        CREATE TABLE class_members (
            class_id       text NOT NULL REFERENCES classes (class_id) ON DELETE CASCADE,
            user_id        text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
            state          text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'active', 'removed')),
            share_progress boolean NOT NULL DEFAULT false,
            consented_at   text,
            joined_at      text NOT NULL,
            updated_at     text NOT NULL,
            PRIMARY KEY (class_id, user_id)
        );
        CREATE INDEX class_members_by_user ON class_members (user_id);
        """,
    ),
    (
        "0011_publishing",
        """
        -- A book a teacher has shared, pinned at one version, with the basis
        -- they attested for sharing it. One pin per book, so a student in two
        -- of the teacher's classes never meets two versions of it.
        CREATE TABLE published_books (
            document_id  text PRIMARY KEY REFERENCES documents (document_id) ON DELETE CASCADE,
            teacher_id   text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
            version      text NOT NULL,
            basis        text NOT NULL CHECK (basis IN ('public_domain', 'government_textbook',
                             'publisher_permission', 'own_work', 'other')),
            note         text,
            attested_at  text NOT NULL,
            published_at text NOT NULL
        );

        -- The prepared pages at the pinned version, so the owner can go on to
        -- a new version while the class reads this one.
        CREATE TABLE prepared_versions (
            document_id text NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE,
            version     text NOT NULL,
            payload     text NOT NULL,
            PRIMARY KEY (document_id, version)
        );

        -- Which classes a published book is shared with.
        CREATE TABLE class_books (
            class_id    text NOT NULL REFERENCES classes (class_id) ON DELETE CASCADE,
            document_id text NOT NULL
                REFERENCES published_books (document_id) ON DELETE CASCADE,
            added_at    text NOT NULL,
            PRIMARY KEY (class_id, document_id)
        );
        CREATE INDEX class_books_by_document ON class_books (document_id);

        -- The teacher's decision on each page flagged for review, per version.
        -- A withheld page is never read to the class, nor searched, nor quizzed.
        CREATE TABLE page_reviews (
            document_id text NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE,
            version     text NOT NULL,
            page_index  integer NOT NULL,
            decision    text NOT NULL CHECK (decision IN ('accepted', 'withheld')),
            decided_at  text NOT NULL,
            PRIMARY KEY (document_id, version, page_index)
        );
        """,
    ),
    (
        "0012_teacher_resets",
        """
        -- A thirty-minute, single-use code a teacher made for one of their
        -- students. Beside the student's own recovery code, never in place of
        -- it. One per student: a new one replaces the last. Kept after use
        -- until the student has been told about it.
        CREATE TABLE teacher_resets (
            user_id    text PRIMARY KEY REFERENCES users (user_id) ON DELETE CASCADE,
            code_hash  text NOT NULL,
            issued_by  text REFERENCES users (user_id) ON DELETE SET NULL,
            issued_at  text NOT NULL,
            expires_at text NOT NULL,
            used_at    text,
            seen_at    text
        );
        """,
    ),
)


#: An arbitrary constant, held by whichever process is migrating.
#:
#: Any number would do; it only has to be the same in every process and unlike
#: anything else that takes an advisory lock on this database.
_MIGRATION_LOCK = 0x51_4D_49_47  # "SMIG"


def migrate(url: str) -> list[str]:
    """Bring a database up to date. Returns the migrations it applied.

    Safe to run on every start-up, and safe to run in **several processes at
    once**, which is the case that actually happens: `docker compose up` starts
    the API and the worker together and both migrate before serving.

    Without the lock below, both read the same "already applied" set before
    either writes to it, and both run the same `ALTER TABLE`. One wins; the
    other gets `DuplicateColumn` and exits, so the stack comes up with a service
    missing and a stack trace that looks like a schema problem rather than a
    race. The bookkeeping row is not enough on its own: it is written *after*
    the DDL, and by then the other process has already read past it.

    `pg_advisory_lock` is a plain blocking lock held on the session, so the
    second process waits, then finds the work done and applies nothing. It is
    released when the connection closes, including when the process dies
    part-way, so a crashed migration does not wedge every future start-up.
    """
    applied: list[str] = []
    with Connection.connect(url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  name       text PRIMARY KEY,"
                "  applied_at timestamptz NOT NULL DEFAULT now()"
                ")"
            )
            done = {
                row[0]
                for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
            }
            for name, sql in MIGRATIONS:
                if name in done:
                    continue
                with connection.transaction():
                    connection.execute(sql)
                    connection.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
                applied.append(name)
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
    return applied


# --- the store -------------------------------------------------------------


class PostgresStore(Store):
    """Documents, jobs, audio and reading positions that survive a restart.

    The connection pool is opened once and shared. Nothing here holds a
    connection across a request: every method borrows one, does its work, and
    gives it back, so a slow synthesis cannot exhaust the pool by sitting on a
    connection it is not using.
    """

    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self._pool = ConnectionPool(
            url, min_size=min_size, max_size=max_size, kwargs={"row_factory": dict_row}, open=True
        )
        self._closed = threading.Event()

    def close(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            self._pool.close()

    # -- documents ---------------------------------------------------------

    def put_document(self, document: Document) -> Document:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO documents (document_id, owner, filename, size_bytes, created_at,
                                       version, title, page_count, segment_count, notes)
                VALUES (%(document_id)s, %(owner)s, %(filename)s, %(size_bytes)s, %(created_at)s,
                        %(version)s, %(title)s, %(page_count)s, %(segment_count)s, %(notes)s)
                ON CONFLICT (document_id) DO UPDATE SET
                    filename      = EXCLUDED.filename,
                    size_bytes    = EXCLUDED.size_bytes,
                    version       = EXCLUDED.version,
                    title         = EXCLUDED.title,
                    page_count    = EXCLUDED.page_count,
                    segment_count = EXCLUDED.segment_count,
                    notes         = EXCLUDED.notes
                """,
                {
                    "document_id": document.document_id,
                    "owner": document.owner,
                    "filename": document.filename,
                    "size_bytes": document.size_bytes,
                    "created_at": document.created_at,
                    "version": document.version,
                    "title": document.title,
                    "page_count": document.page_count,
                    "segment_count": document.segment_count,
                    "notes": list(document.notes),
                },
            )
        return document

    def get_document(self, document_id: str, owner: str) -> Document | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = %s AND owner = %s",
                (document_id, owner),
            ).fetchone()
        return _document(row) if row else None

    def list_documents(self, owner: str) -> list[Document]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE owner = %s ORDER BY created_at DESC",
                (owner,),
            ).fetchall()
        return [_document(row) for row in rows]

    def delete_document(self, document_id: str, owner: str) -> bool:
        """One statement. The cascade removes the source, jobs, audio and position."""
        with self._pool.connection() as connection:
            result = connection.execute(
                "DELETE FROM documents WHERE document_id = %s AND owner = %s",
                (document_id, owner),
            )
            return result.rowcount > 0

    def put_source(self, document_id: str, data: bytes) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO sources (document_id, data) VALUES (%s, %s)
                ON CONFLICT (document_id) DO UPDATE SET data = EXCLUDED.data
                """,
                (document_id, data),
            )

    def get_source(self, document_id: str) -> bytes | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT data FROM sources WHERE document_id = %s", (document_id,)
            ).fetchone()
        return bytes(row["data"]) if row else None

    def put_prepared(self, document_id: str, payload: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO prepared (document_id, payload) VALUES (%s, %s)
                ON CONFLICT (document_id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (document_id, payload),
            )

    def get_prepared(self, document_id: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM prepared WHERE document_id = %s", (document_id,)
            ).fetchone()
        return row["payload"] if row else None

    # -- jobs --------------------------------------------------------------

    def put_job(self, job: Job) -> Job:
        job = replace(job, updated_at=_now())
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (job_id, document_id, owner, kind, state, stage, detail,
                                  created_at, updated_at, lease_expires_at,
                                  pages_done, pages_total)
                VALUES (%(job_id)s, %(document_id)s, %(owner)s, %(kind)s, %(state)s, %(stage)s,
                        %(detail)s, %(created_at)s, %(updated_at)s, %(lease_expires_at)s,
                        %(pages_done)s, %(pages_total)s)
                ON CONFLICT (job_id) DO UPDATE SET
                    state            = EXCLUDED.state,
                    stage            = EXCLUDED.stage,
                    detail           = EXCLUDED.detail,
                    updated_at       = EXCLUDED.updated_at,
                    lease_expires_at = EXCLUDED.lease_expires_at,
                    pages_done       = EXCLUDED.pages_done,
                    pages_total      = EXCLUDED.pages_total
                """,
                {
                    "job_id": job.job_id,
                    "document_id": job.document_id,
                    "owner": job.owner,
                    "kind": job.kind,
                    "state": str(job.state),
                    "stage": job.stage,
                    "detail": job.detail,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                    "lease_expires_at": job.lease_expires_at,
                    "pages_done": job.pages_done,
                    "pages_total": job.pages_total,
                },
            )
        return job

    def get_job(self, job_id: str, owner: str) -> Job | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = %s AND owner = %s", (job_id, owner)
            ).fetchone()
        return _job(row) if row else None

    def get_job_for_worker(self, job_id: str) -> Job | None:
        """The one deliberately unscoped read. See ``Store.get_job_for_worker``."""
        with self._pool.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,)).fetchone()
        return _job(row) if row else None

    def renew_lease(self, job_id: str, until: str) -> bool:
        """The heartbeat. See ``Store.renew_lease``.

        The state is in the WHERE clause rather than checked first, so a
        heartbeat racing the reaper can never revive a job it has just failed.
        """
        with self._pool.connection() as connection:
            renewed = connection.execute(
                "UPDATE jobs SET lease_expires_at = %s WHERE job_id = %s AND state = 'running'",
                (until, job_id),
            ).rowcount
        return renewed == 1

    def report_progress(self, job_id: str, stage: str, done: int, total: int) -> bool:
        """See ``Store.report_progress``. The state is in the WHERE clause, as
        in :meth:`renew_lease`, so a late report cannot move a finished job."""
        with self._pool.connection() as connection:
            updated = connection.execute(
                """
                UPDATE jobs
                   SET stage = %(stage)s, pages_done = %(done)s, pages_total = %(total)s,
                       updated_at = %(now)s
                 WHERE job_id = %(job_id)s AND state = 'running'
                """,
                {"stage": stage, "done": done, "total": total, "now": _now(), "job_id": job_id},
            ).rowcount
        return updated == 1

    def fail_stalled_jobs(self, now: str, stale_before: str, detail: str) -> list[str]:
        """See ``Store.fail_stalled_jobs``. One statement, so it is idempotent."""
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                UPDATE jobs
                   SET state = 'failed', stage = 'stalled', detail = %(detail)s,
                       lease_expires_at = NULL, updated_at = %(now)s
                 WHERE state = 'running'
                   AND (   (lease_expires_at IS NOT NULL AND lease_expires_at < %(now)s)
                        OR (lease_expires_at IS NULL AND updated_at < %(stale_before)s))
                RETURNING job_id
                """,
                {"now": now, "stale_before": stale_before, "detail": detail},
            ).fetchall()
        return [row["job_id"] for row in rows]

    def latest_jobs(self, owner: str) -> dict[str, Job]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (document_id) *
                  FROM jobs
                 WHERE owner = %s
                 ORDER BY document_id, created_at DESC
                """,
                (owner,),
            ).fetchall()
        return {row["document_id"]: _job(row) for row in rows}

    def jobs_for(self, document_id: str, owner: str) -> list[Job]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE document_id = %s AND owner = %s ORDER BY created_at",
                (document_id, owner),
            ).fetchall()
        return [_job(row) for row in rows]

    # -- audio -------------------------------------------------------------

    def put_audio(self, record: AudioRecord) -> AudioRecord:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO audio (cache_key, document_id, owner, segment_id, wav,
                                   duration_seconds, is_real_model, voice_id, model_version)
                VALUES (%(cache_key)s, %(document_id)s, %(owner)s, %(segment_id)s, %(wav)s,
                        %(duration_seconds)s, %(is_real_model)s, %(voice_id)s, %(model_version)s)
                ON CONFLICT (document_id, cache_key) DO NOTHING
                """,
                {
                    "cache_key": record.cache_key,
                    "document_id": record.document_id,
                    "owner": record.owner,
                    "segment_id": record.segment_id,
                    "wav": record.wav,
                    "duration_seconds": record.duration_seconds,
                    "is_real_model": record.is_real_model,
                    "voice_id": record.voice_id,
                    "model_version": record.model_version,
                },
            )
        return record

    def get_audio(self, cache_key: str, document_id: str, owner: str) -> AudioRecord | None:
        """Cached audio is still private content, so the owner is in the query.

        The cache key is derived from text and settings, so two readers with the
        same book produce the same key. Each document keeps its own row, and the
        owner clause means one reader is never served another's audio because it
        happened to be generated first.
        """
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM audio WHERE document_id = %s AND cache_key = %s AND owner = %s",
                (document_id, cache_key, owner),
            ).fetchone()
        return _audio(row) if row else None

    # -- progress ----------------------------------------------------------

    def put_progress(self, progress: Progress) -> Progress:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO progress (document_id, owner, document_version, segment_id,
                                      offset_seconds, updated_at, segment_index)
                VALUES (%(document_id)s, %(owner)s, %(document_version)s, %(segment_id)s,
                        %(offset_seconds)s, %(updated_at)s, %(segment_index)s)
                ON CONFLICT (document_id, owner) DO UPDATE SET
                    document_version = EXCLUDED.document_version,
                    segment_id       = EXCLUDED.segment_id,
                    offset_seconds   = EXCLUDED.offset_seconds,
                    updated_at       = EXCLUDED.updated_at,
                    segment_index    = EXCLUDED.segment_index
                """,
                {
                    "document_id": progress.document_id,
                    "owner": progress.owner,
                    "document_version": progress.document_version,
                    "segment_id": progress.segment_id,
                    "offset_seconds": progress.offset_seconds,
                    "updated_at": progress.updated_at,
                    "segment_index": progress.segment_index,
                },
            )
        return progress

    def get_progress(self, document_id: str, owner: str) -> Progress | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM progress WHERE document_id = %s AND owner = %s",
                (document_id, owner),
            ).fetchone()
        return _progress(row) if row else None

    def list_progress(self, owner: str) -> dict[str, Progress]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM progress WHERE owner = %s", (owner,)
            ).fetchall()
        return {row["document_id"]: _progress(row) for row in rows}

    # -- bookmarks ---------------------------------------------------------

    def put_bookmark(self, bookmark: Bookmark) -> tuple[Bookmark, bool]:
        """Insert, or update the one already on this segment.

        ``RETURNING`` gives back the row as it now stands, which is how a
        second bookmark on the same sentence comes back with the *first* one's
        id and creation time rather than the ones this call proposed. The
        ``xmax`` test distinguishes an insert from an update: it is zero on a
        freshly inserted row and carries the updating transaction on one that
        ``ON CONFLICT`` updated. It goes through ``text`` because there is no
        comparison operator between ``xid`` and an integer.
        """
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO bookmarks (bookmark_id, document_id, owner, document_version,
                                       segment_id, note, created_at)
                VALUES (%(bookmark_id)s, %(document_id)s, %(owner)s, %(document_version)s,
                        %(segment_id)s, %(note)s, %(created_at)s)
                ON CONFLICT (owner, document_id, segment_id) DO UPDATE SET
                    document_version = EXCLUDED.document_version,
                    note             = EXCLUDED.note
                RETURNING *, (xmax::text::bigint <> 0) AS updated
                """,
                {
                    "bookmark_id": bookmark.bookmark_id,
                    "document_id": bookmark.document_id,
                    "owner": bookmark.owner,
                    "document_version": bookmark.document_version,
                    "segment_id": bookmark.segment_id,
                    "note": bookmark.note,
                    "created_at": bookmark.created_at,
                },
            ).fetchone()
        assert row is not None
        return _bookmark(row), not row["updated"]

    def list_bookmarks(self, document_id: str, owner: str) -> list[Bookmark]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM bookmarks
                WHERE document_id = %s AND owner = %s
                ORDER BY created_at
                """,
                (document_id, owner),
            ).fetchall()
        return [_bookmark(row) for row in rows]

    def get_bookmark(self, bookmark_id: str, owner: str) -> Bookmark | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM bookmarks WHERE bookmark_id = %s AND owner = %s",
                (bookmark_id, owner),
            ).fetchone()
        return _bookmark(row) if row else None

    def delete_bookmark(self, bookmark_id: str, owner: str) -> bool:
        with self._pool.connection() as connection:
            result = connection.execute(
                "DELETE FROM bookmarks WHERE bookmark_id = %s AND owner = %s",
                (bookmark_id, owner),
            )
            return result.rowcount > 0

    # -- accounts ----------------------------------------------------------

    def put_user(self, user: User) -> User:
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO users (user_id, email, email_key, password_hash,
                                       display_name, created_at, role, recovery_hash)
                    VALUES (%(user_id)s, %(email)s, %(email_key)s, %(password_hash)s,
                            %(display_name)s, %(created_at)s, %(role)s, %(recovery_hash)s)
                    -- role and recovery_hash are deliberately not updated: they
                    -- have their own methods, so a stale copy written back
                    -- cannot demote a teacher or revive a used code.
                    ON CONFLICT (user_id) DO UPDATE SET
                        email         = EXCLUDED.email,
                        email_key     = EXCLUDED.email_key,
                        password_hash = EXCLUDED.password_hash,
                        display_name  = EXCLUDED.display_name
                    """,
                    {
                        "user_id": user.user_id,
                        "email": user.email,
                        "email_key": user.email_key,
                        "password_hash": user.password_hash,
                        "display_name": user.display_name,
                        "created_at": user.created_at,
                        "role": str(user.role),
                        "recovery_hash": user.recovery_hash,
                    },
                )
        except UniqueViolation as clash:
            # The unique index on email_key, not the primary key: the ON
            # CONFLICT above handles a repeat of the same user_id, so the only
            # way here is a second account claiming an address.
            raise EmailTaken(user.email_key) from clash
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = %s", (user_id,)
            ).fetchone()
        return _user(row) if row else None

    def get_user_by_email(self, email_key: str) -> User | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email_key = %s", (email_key,)
            ).fetchone()
        return _user(row) if row else None

    def delete_user(self, user_id: str) -> bool:
        """One statement. The cascade removes sessions and audit events."""
        with self._pool.connection() as connection:
            deleted = connection.execute(
                "DELETE FROM users WHERE user_id = %s", (user_id,)
            ).rowcount
        return deleted == 1

    def set_role(self, user_id: str, role: Role) -> bool:
        with self._pool.connection() as connection:
            changed = connection.execute(
                "UPDATE users SET role = %s WHERE user_id = %s", (str(role), user_id)
            ).rowcount
        return changed == 1

    def set_recovery_hash(self, user_id: str, recovery_hash: str | None) -> bool:
        with self._pool.connection() as connection:
            changed = connection.execute(
                "UPDATE users SET recovery_hash = %s WHERE user_id = %s", (recovery_hash, user_id)
            ).rowcount
        return changed == 1

    def put_invite(self, invite: TeacherInvite) -> TeacherInvite:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO teacher_invites (code_hash, created_by, created_at, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (invite.code_hash, invite.created_by, invite.created_at, invite.expires_at),
            )
        return invite

    def redeem_invite(self, code_hash: str, user_id: str, now: str) -> bool:
        """See ``Store.redeem_invite``. One statement: check and spend together."""
        with self._pool.connection() as connection:
            spent = connection.execute(
                """
                UPDATE teacher_invites SET used_by = %(user_id)s, used_at = %(now)s
                 WHERE code_hash = %(code_hash)s AND used_at IS NULL AND expires_at > %(now)s
                """,
                {"user_id": user_id, "now": now, "code_hash": code_hash},
            ).rowcount
        return spent == 1

    def put_teacher_reset(self, reset: TeacherReset) -> TeacherReset:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO teacher_resets
                    (user_id, code_hash, issued_by, issued_at, expires_at, used_at, seen_at)
                VALUES (%(user_id)s, %(code_hash)s, %(issued_by)s, %(issued_at)s,
                        %(expires_at)s, %(used_at)s, %(seen_at)s)
                ON CONFLICT (user_id) DO UPDATE SET
                    code_hash = EXCLUDED.code_hash, issued_by = EXCLUDED.issued_by,
                    issued_at = EXCLUDED.issued_at, expires_at = EXCLUDED.expires_at,
                    used_at = EXCLUDED.used_at, seen_at = EXCLUDED.seen_at
                """,
                {
                    "user_id": reset.user_id,
                    "code_hash": reset.code_hash,
                    "issued_by": reset.issued_by,
                    "issued_at": reset.issued_at,
                    "expires_at": reset.expires_at,
                    "used_at": reset.used_at,
                    "seen_at": reset.seen_at,
                },
            )
        return reset

    def teacher_reset(self, user_id: str) -> TeacherReset | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM teacher_resets WHERE user_id = %s", (user_id,)
            ).fetchone()
        return TeacherReset(**row) if row else None

    def spend_teacher_reset(self, user_id: str, code_hash: str, now: str) -> bool:
        """See ``Store.spend_teacher_reset``. One statement: check and spend together."""
        with self._pool.connection() as connection:
            spent = connection.execute(
                """
                UPDATE teacher_resets SET used_at = %(now)s
                 WHERE user_id = %(user_id)s AND code_hash = %(code_hash)s
                   AND used_at IS NULL AND expires_at > %(now)s
                """,
                {"user_id": user_id, "code_hash": code_hash, "now": now},
            ).rowcount
        return spent == 1

    def acknowledge_teacher_reset(self, user_id: str, now: str) -> bool:
        with self._pool.connection() as connection:
            seen = connection.execute(
                """
                UPDATE teacher_resets SET seen_at = %s
                 WHERE user_id = %s AND seen_at IS NULL
                """,
                (now, user_id),
            ).rowcount
        return seen == 1

    def record(self, event: AuditEvent) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (event_id, kind, actor, subject, reason, at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (event.event_id, event.kind, event.actor, event.subject, event.reason, event.at),
            )

    def audit_for(self, subject: str) -> list[AuditEvent]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE subject = %s ORDER BY at", (subject,)
            ).fetchall()
        return [
            AuditEvent(
                event_id=row["event_id"],
                kind=row["kind"],
                actor=row["actor"],
                subject=row["subject"],
                reason=row["reason"],
                at=row["at"],
            )
            for row in rows
        ]

    def put_session(self, session: Session) -> Session:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (token_hash) DO UPDATE SET expires_at = EXCLUDED.expires_at
                """,
                (session.token_hash, session.user_id, session.created_at, session.expires_at),
            )
        return session

    def get_session(self, token_hash: str) -> Session | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE token_hash = %s", (token_hash,)
            ).fetchone()
        return _session(row) if row else None

    def delete_session(self, token_hash: str) -> bool:
        with self._pool.connection() as connection:
            result = connection.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))
            return result.rowcount > 0

    def delete_sessions_for_user(self, user_id: str) -> int:
        with self._pool.connection() as connection:
            result = connection.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            return result.rowcount

    # -- publishing ----------------------------------------------------------

    def readable_document(self, document_id: str, reader: str) -> Reading | None:
        """The one reading predicate: the owner, or an active member of a class
        the book is published to, at the published version."""
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT d.*, NULL AS pinned
                  FROM documents d
                 WHERE d.document_id = %(doc)s AND d.owner = %(reader)s
                UNION ALL
                SELECT d.*, p.version AS pinned
                  FROM documents d
                  JOIN published_books p ON p.document_id = d.document_id
                  JOIN class_books cb ON cb.document_id = d.document_id
                  JOIN class_members m ON m.class_id = cb.class_id
                 WHERE d.document_id = %(doc)s
                   AND m.user_id = %(reader)s AND m.state = 'active'
                 LIMIT 1
                """,
                {"doc": document_id, "reader": reader},
            ).fetchone()
            if row is None:
                return None
            document = _document(row)
            if row["pinned"] is None:
                return Reading(document=document, as_owner=True)
            withheld = connection.execute(
                """
                SELECT page_index FROM page_reviews
                 WHERE document_id = %s AND version = %s AND decision = 'withheld'
                """,
                (document_id, row["pinned"]),
            ).fetchall()
        return Reading(
            document=replace(document, version=row["pinned"]),
            as_owner=False,
            withheld=frozenset(r["page_index"] for r in withheld),
        )

    def put_page_review(
        self, document_id: str, owner: str, version: str, page_index: int, decision: PageDecision
    ) -> bool:
        with self._pool.connection() as connection:
            written = connection.execute(
                """
                INSERT INTO page_reviews (document_id, version, page_index, decision, decided_at)
                SELECT d.document_id, %(version)s, %(page)s, %(decision)s, %(now)s
                  FROM documents d WHERE d.document_id = %(doc)s AND d.owner = %(owner)s
                ON CONFLICT (document_id, version, page_index) DO UPDATE SET
                    decision = EXCLUDED.decision, decided_at = EXCLUDED.decided_at
                """,
                {
                    "version": version,
                    "page": page_index,
                    "decision": str(decision),
                    "now": _now(),
                    "doc": document_id,
                    "owner": owner,
                },
            ).rowcount
        return written == 1

    def page_reviews(self, document_id: str, owner: str, version: str) -> dict[int, PageDecision]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT r.page_index, r.decision
                  FROM page_reviews r JOIN documents d USING (document_id)
                 WHERE r.document_id = %s AND d.owner = %s AND r.version = %s
                """,
                (document_id, owner, version),
            ).fetchall()
        return {row["page_index"]: PageDecision(row["decision"]) for row in rows}

    def publish(self, publication: Publication, class_ids: list[str], payload: str) -> bool:
        with self._pool.connection() as connection, connection.transaction():
            owns = connection.execute(
                "SELECT 1 FROM documents WHERE document_id = %s AND owner = %s",
                (publication.document_id, publication.teacher_id),
            ).fetchone()
            taught = connection.execute(
                "SELECT count(*) AS n FROM classes WHERE class_id = ANY(%s) AND teacher_id = %s",
                (class_ids, publication.teacher_id),
            ).fetchone()
            if owns is None or taught["n"] != len(set(class_ids)):
                return False
            connection.execute(
                """
                INSERT INTO published_books
                    (document_id, teacher_id, version, basis, note, attested_at, published_at)
                VALUES (%(doc)s, %(teacher)s, %(version)s, %(basis)s, %(note)s,
                        %(attested)s, %(published)s)
                ON CONFLICT (document_id) DO UPDATE SET
                    version = EXCLUDED.version, basis = EXCLUDED.basis, note = EXCLUDED.note,
                    attested_at = EXCLUDED.attested_at, published_at = EXCLUDED.published_at
                """,
                {
                    "doc": publication.document_id,
                    "teacher": publication.teacher_id,
                    "version": publication.version,
                    "basis": str(publication.basis),
                    "note": publication.note,
                    "attested": publication.attested_at,
                    "published": publication.published_at,
                },
            )
            connection.execute(
                """
                INSERT INTO prepared_versions (document_id, version, payload) VALUES (%s, %s, %s)
                ON CONFLICT (document_id, version) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (publication.document_id, publication.version, payload),
            )
            for class_id in class_ids:
                connection.execute(
                    """
                    INSERT INTO class_books (class_id, document_id, added_at) VALUES (%s, %s, %s)
                    ON CONFLICT (class_id, document_id) DO NOTHING
                    """,
                    (class_id, publication.document_id, publication.published_at),
                )
        return True

    def unpublish(self, document_id: str, owner: str, class_id: str) -> bool:
        with self._pool.connection() as connection:
            deleted = connection.execute(
                """
                DELETE FROM class_books
                 WHERE class_id = %s AND document_id = %s
                   AND document_id IN (SELECT document_id FROM documents WHERE owner = %s)
                """,
                (class_id, document_id, owner),
            ).rowcount
        return deleted == 1

    def publication(self, document_id: str, owner: str) -> tuple[Publication, list[str]] | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT p.* FROM published_books p JOIN documents d USING (document_id)
                 WHERE p.document_id = %s AND d.owner = %s
                """,
                (document_id, owner),
            ).fetchone()
            if row is None:
                return None
            classes = connection.execute(
                "SELECT class_id FROM class_books WHERE document_id = %s ORDER BY class_id",
                (document_id,),
            ).fetchall()
        publication = Publication(
            document_id=row["document_id"],
            teacher_id=row["teacher_id"],
            version=row["version"],
            basis=RightsBasis(row["basis"]),
            note=row["note"],
            attested_at=row["attested_at"],
            published_at=row["published_at"],
        )
        return publication, [r["class_id"] for r in classes]

    def get_prepared_version(self, document_id: str, version: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM prepared_versions WHERE document_id = %s AND version = %s",
                (document_id, version),
            ).fetchone()
        return row["payload"] if row else None

    def class_books(self, reader: str) -> list[tuple[Classroom, Document]]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT c.class_id, c.teacher_id, c.name, c.join_code, c.created_at AS class_created,
                       d.*, p.version AS pinned
                  FROM class_members m
                  JOIN classes c ON c.class_id = m.class_id
                  JOIN class_books cb ON cb.class_id = m.class_id
                  JOIN published_books p ON p.document_id = cb.document_id
                  JOIN documents d ON d.document_id = cb.document_id
                 WHERE m.user_id = %s AND m.state = 'active' AND d.owner <> m.user_id
                 ORDER BY c.class_id, cb.document_id
                """,
                (reader,),
            ).fetchall()
        return [
            (
                Classroom(
                    class_id=row["class_id"],
                    teacher_id=row["teacher_id"],
                    name=row["name"],
                    join_code=row["join_code"],
                    created_at=row["class_created"],
                ),
                replace(_document(row), version=row["pinned"]),
            )
            for row in rows
        ]

    # -- classes -----------------------------------------------------------

    def put_class(self, classroom: Classroom) -> Classroom:
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO classes (class_id, teacher_id, name, join_code, created_at)
                    VALUES (%(class_id)s, %(teacher_id)s, %(name)s, %(join_code)s, %(created_at)s)
                    ON CONFLICT (class_id) DO UPDATE SET
                        name = EXCLUDED.name, join_code = EXCLUDED.join_code
                    """,
                    {
                        "class_id": classroom.class_id,
                        "teacher_id": classroom.teacher_id,
                        "name": classroom.name,
                        "join_code": classroom.join_code,
                        "created_at": classroom.created_at,
                    },
                )
        except UniqueViolation as clash:
            raise CodeTaken(classroom.join_code) from clash
        return classroom

    def class_taught(self, class_id: str, teacher_id: str) -> Classroom | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM classes WHERE class_id = %s AND teacher_id = %s",
                (class_id, teacher_id),
            ).fetchone()
        return _classroom(row) if row else None

    def classes_taught(self, teacher_id: str) -> list[Classroom]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM classes WHERE teacher_id = %s ORDER BY created_at", (teacher_id,)
            ).fetchall()
        return [_classroom(row) for row in rows]

    def class_by_code(self, join_code: str) -> Classroom | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM classes WHERE join_code = %s", (join_code,)
            ).fetchone()
        return _classroom(row) if row else None

    def set_join_code(self, class_id: str, teacher_id: str, join_code: str) -> bool:
        try:
            with self._pool.connection() as connection:
                changed = connection.execute(
                    "UPDATE classes SET join_code = %s WHERE class_id = %s AND teacher_id = %s",
                    (join_code, class_id, teacher_id),
                ).rowcount
        except UniqueViolation as clash:
            raise CodeTaken(join_code) from clash
        return changed == 1

    def delete_class(self, class_id: str, teacher_id: str) -> bool:
        with self._pool.connection() as connection:
            deleted = connection.execute(
                "DELETE FROM classes WHERE class_id = %s AND teacher_id = %s",
                (class_id, teacher_id),
            ).rowcount
        return deleted == 1

    def join_class(self, class_id: str, user_id: str) -> Membership:
        now = _now()
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO class_members (class_id, user_id, state, joined_at, updated_at)
                VALUES (%(class_id)s, %(user_id)s, 'pending', %(now)s, %(now)s)
                ON CONFLICT (class_id, user_id) DO UPDATE SET
                    -- A removed member asking again starts over as pending;
                    -- anyone else is left exactly as they were.
                    state = CASE WHEN class_members.state = 'removed' THEN 'pending'
                                 ELSE class_members.state END,
                    share_progress = CASE WHEN class_members.state = 'removed' THEN false
                                          ELSE class_members.share_progress END,
                    consented_at = CASE WHEN class_members.state = 'removed' THEN NULL
                                        ELSE class_members.consented_at END,
                    joined_at = CASE WHEN class_members.state = 'removed' THEN EXCLUDED.joined_at
                                     ELSE class_members.joined_at END,
                    updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                {"class_id": class_id, "user_id": user_id, "now": now},
            ).fetchone()
        return _membership(row)

    def membership(self, class_id: str, user_id: str) -> Membership | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM class_members WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            ).fetchone()
        return _membership(row) if row else None

    def classes_joined(self, user_id: str) -> list[tuple[Classroom, Membership]]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT c.class_id, c.teacher_id, c.name, c.join_code, c.created_at,
                       m.user_id, m.state, m.share_progress, m.consented_at,
                       m.joined_at, m.updated_at
                  FROM class_members m JOIN classes c USING (class_id)
                 WHERE m.user_id = %s AND m.state <> 'removed'
                 ORDER BY m.joined_at
                """,
                (user_id,),
            ).fetchall()
        return [(_classroom(row), _membership(row)) for row in rows]

    def members(self, class_id: str, teacher_id: str) -> list[Membership]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT m.* FROM class_members m JOIN classes c USING (class_id)
                 WHERE m.class_id = %s AND c.teacher_id = %s
                 ORDER BY m.joined_at
                """,
                (class_id, teacher_id),
            ).fetchall()
        return [_membership(row) for row in rows]

    def set_member_state(
        self, class_id: str, teacher_id: str, user_id: str, state: MemberState
    ) -> bool:
        with self._pool.connection() as connection:
            changed = connection.execute(
                """
                UPDATE class_members SET state = %(state)s, updated_at = %(now)s
                 WHERE class_id = %(class_id)s AND user_id = %(user_id)s
                   AND class_id IN (SELECT class_id FROM classes WHERE teacher_id = %(teacher)s)
                """,
                {
                    "state": str(state),
                    "now": _now(),
                    "class_id": class_id,
                    "user_id": user_id,
                    "teacher": teacher_id,
                },
            ).rowcount
        return changed == 1

    def leave_class(self, class_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            deleted = connection.execute(
                "DELETE FROM class_members WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            ).rowcount
        return deleted == 1

    def set_share_progress(self, class_id: str, user_id: str, share: bool) -> bool:
        now = _now()
        with self._pool.connection() as connection:
            changed = connection.execute(
                """
                UPDATE class_members
                   SET share_progress = %(share)s, updated_at = %(now)s,
                       consented_at = CASE WHEN %(share)s THEN %(now)s ELSE NULL END
                 WHERE class_id = %(class_id)s AND user_id = %(user_id)s AND state <> 'removed'
                """,
                {"share": share, "now": now, "class_id": class_id, "user_id": user_id},
            ).rowcount
        return changed == 1

    # -- tests -------------------------------------------------------------

    def reset_for_tests(self) -> None:
        """Empty every table. Named so it can never be mistaken for a feature.

        The contract suite runs each test against a clean database. Truncating
        ``documents`` cascades to everything else, which is the same property
        deletion relies on — so if the cascade were wrong, this would leave rows
        behind and the deletion tests would fail.
        """
        with self._pool.connection() as connection:
            connection.execute("TRUNCATE documents, users CASCADE")


# --- rows to dataclasses ---------------------------------------------------


def _classroom(row: dict[str, Any]) -> Classroom:
    return Classroom(
        class_id=row["class_id"],
        teacher_id=row["teacher_id"],
        name=row["name"],
        join_code=row["join_code"],
        created_at=row["created_at"],
    )


def _membership(row: dict[str, Any]) -> Membership:
    return Membership(
        class_id=row["class_id"],
        user_id=row["user_id"],
        state=MemberState(row["state"]),
        share_progress=row["share_progress"],
        consented_at=row["consented_at"],
        joined_at=row["joined_at"],
        updated_at=row["updated_at"],
    )


def _document(row: dict[str, Any]) -> Document:
    return Document(
        document_id=row["document_id"],
        owner=row["owner"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
        version=row["version"],
        title=row["title"],
        page_count=row["page_count"],
        segment_count=row["segment_count"],
        # A tuple, because the dataclass promises one and a list would compare
        # unequal to the value that went in.
        notes=tuple(row["notes"]),
    )


def _job(row: dict[str, Any]) -> Job:
    return Job(
        job_id=row["job_id"],
        document_id=row["document_id"],
        owner=row["owner"],
        kind=row["kind"],
        state=JobState(row["state"]),
        stage=row["stage"],
        detail=row["detail"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        lease_expires_at=row["lease_expires_at"],
        pages_done=row["pages_done"],
        pages_total=row["pages_total"],
    )


def _audio(row: dict[str, Any]) -> AudioRecord:
    return AudioRecord(
        cache_key=row["cache_key"],
        document_id=row["document_id"],
        owner=row["owner"],
        segment_id=row["segment_id"],
        wav=bytes(row["wav"]),
        duration_seconds=row["duration_seconds"],
        is_real_model=row["is_real_model"],
        voice_id=row["voice_id"],
        model_version=row["model_version"],
    )


def _progress(row: dict[str, Any]) -> Progress:
    return Progress(
        document_id=row["document_id"],
        owner=row["owner"],
        document_version=row["document_version"],
        segment_id=row["segment_id"],
        offset_seconds=row["offset_seconds"],
        updated_at=row["updated_at"],
        segment_index=row["segment_index"],
    )


def _bookmark(row: dict[str, Any]) -> Bookmark:
    return Bookmark(
        bookmark_id=row["bookmark_id"],
        document_id=row["document_id"],
        owner=row["owner"],
        document_version=row["document_version"],
        segment_id=row["segment_id"],
        note=row["note"],
        created_at=row["created_at"],
    )


def _user(row: dict[str, Any]) -> User:
    return User(
        user_id=row["user_id"],
        email=row["email"],
        email_key=row["email_key"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
        created_at=row["created_at"],
        role=Role(row["role"]),
        recovery_hash=row["recovery_hash"],
    )


def _session(row: dict[str, Any]) -> Session:
    return Session(
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )
