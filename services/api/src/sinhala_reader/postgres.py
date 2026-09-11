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
    Bookmark,
    Document,
    EmailTaken,
    Job,
    JobState,
    Progress,
    Session,
    Store,
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
)


def migrate(url: str) -> list[str]:
    """Bring a database up to date. Returns the migrations it applied.

    Safe to run on every start-up: each migration runs once, inside its own
    transaction with the bookkeeping row, so an interrupted migration is not
    recorded as applied.
    """
    applied: list[str] = []
    with Connection.connect(url, autocommit=True) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  name       text PRIMARY KEY,"
            "  applied_at timestamptz NOT NULL DEFAULT now()"
            ")"
        )
        done = {
            row[0] for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }
        for name, sql in MIGRATIONS:
            if name in done:
                continue
            with connection.transaction():
                connection.execute(sql)
                connection.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
            applied.append(name)
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
                                       version, page_count, segment_count, notes)
                VALUES (%(document_id)s, %(owner)s, %(filename)s, %(size_bytes)s, %(created_at)s,
                        %(version)s, %(page_count)s, %(segment_count)s, %(notes)s)
                ON CONFLICT (document_id) DO UPDATE SET
                    filename      = EXCLUDED.filename,
                    size_bytes    = EXCLUDED.size_bytes,
                    version       = EXCLUDED.version,
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
                                  created_at, updated_at)
                VALUES (%(job_id)s, %(document_id)s, %(owner)s, %(kind)s, %(state)s, %(stage)s,
                        %(detail)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (job_id) DO UPDATE SET
                    state      = EXCLUDED.state,
                    stage      = EXCLUDED.stage,
                    detail     = EXCLUDED.detail,
                    updated_at = EXCLUDED.updated_at
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
                ON CONFLICT (cache_key) DO NOTHING
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

    def get_audio(self, cache_key: str, owner: str) -> AudioRecord | None:
        """Cached audio is still private content, so the owner is in the query.

        The cache key is derived from text and settings, so two readers with the
        same book produce the same key; without the owner clause one would be
        served the other's audio because it happened to be generated first.
        """
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM audio WHERE cache_key = %s AND owner = %s", (cache_key, owner)
            ).fetchone()
        return _audio(row) if row else None

    # -- progress ----------------------------------------------------------

    def put_progress(self, progress: Progress) -> Progress:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO progress (document_id, owner, document_version, segment_id,
                                      offset_seconds, updated_at)
                VALUES (%(document_id)s, %(owner)s, %(document_version)s, %(segment_id)s,
                        %(offset_seconds)s, %(updated_at)s)
                ON CONFLICT (document_id, owner) DO UPDATE SET
                    document_version = EXCLUDED.document_version,
                    segment_id       = EXCLUDED.segment_id,
                    offset_seconds   = EXCLUDED.offset_seconds,
                    updated_at       = EXCLUDED.updated_at
                """,
                {
                    "document_id": progress.document_id,
                    "owner": progress.owner,
                    "document_version": progress.document_version,
                    "segment_id": progress.segment_id,
                    "offset_seconds": progress.offset_seconds,
                    "updated_at": progress.updated_at,
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
                                       display_name, created_at)
                    VALUES (%(user_id)s, %(email)s, %(email_key)s, %(password_hash)s,
                            %(display_name)s, %(created_at)s)
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


def _document(row: dict[str, Any]) -> Document:
    return Document(
        document_id=row["document_id"],
        owner=row["owner"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
        version=row["version"],
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
    )


def _session(row: dict[str, Any]) -> Session:
    return Session(
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )
