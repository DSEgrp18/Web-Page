"""What the reader keeps, and the interface a real database will implement.

CLAUDE.md names PostgreSQL, Redis and object storage as the production shape.
The interface is the part that matters: every method takes an ``owner`` and
enforces it, so authorisation is a property of the store rather than something
each endpoint remembers to check.

Two implementations sit behind it, chosen at the composition root:

* ``InMemoryStore`` — a dictionary with a lock. **Nothing survives a restart.**
  It is the default because a test run and a ``--reload`` must not need a
  server, and it is honest about what it is: the health report says so, so
  nobody deploys it by accident.
* ``PostgresStore`` in :mod:`.postgres` — selected by setting
  ``SINHALA_READER_DATABASE_URL``.

Both are held to one suite, ``tests/test_store_contract.py``. CLAUDE.md is
explicit that mocks alone do not validate integration, so that suite runs
against a real database when one is configured and says out loud when it does
not.

Ownership is enforced by returning *nothing* for another owner's document,
never by raising a distinguishable error. A "403 Forbidden" on a document that
exists tells the caller it exists; a 404 does not. For private books belonging to
identifiable students, that difference matters.
"""

from __future__ import annotations

import os
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

#: Where the database is. Unset means the in-memory store.
DATABASE_URL_ENV = "SINHALA_READER_DATABASE_URL"


class EmailTaken(Exception):
    """That address already has an account.

    Raised by the store rather than checked by a route: a check followed by an
    insert leaves a gap that two simultaneous registrations both pass through.
    """


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class JobState(StrEnum):
    """The states CLAUDE.md names, and no others.

    ``cancelled`` is distinct from ``failed`` because a reader who deletes a
    document while it is processing has not encountered an error.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED)


@dataclass(frozen=True)
class Job:
    """A unit of background work a reader can be told about."""

    job_id: str
    document_id: str
    owner: str
    kind: str
    state: JobState = JobState.QUEUED
    stage: str = "queued"
    """Where the work has got to, in words fit to show a person."""

    detail: str | None = None
    """Why it failed, with no document content in it.

    CLAUDE.md forbids logging private passages by default, and a failure
    message is a log line that also reaches a screen.
    """

    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class Document:
    """An uploaded book, and what became of it."""

    document_id: str
    owner: str
    filename: str
    size_bytes: int
    created_at: str = field(default_factory=_now)
    version: str | None = None
    """Set once preparation succeeds. Part of every audio cache key."""

    page_count: int = 0
    segment_count: int = 0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Progress:
    """Where a reader had got to.

    Carries the document version: text that has been corrected since is a
    different document, and dropping the reader at the same segment id in
    changed text would put them somewhere they never were.
    """

    document_id: str
    owner: str
    document_version: str
    segment_id: str
    offset_seconds: float = 0.0
    updated_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class User:
    """A person with an account.

    ``email_key`` is the lowercased email and is what uniqueness is enforced on.
    ``email`` keeps what the reader typed, because a name is theirs to
    capitalise and showing it back changed is a small unkindness.

    The password hash is here; the password never is, anywhere, at any point
    after the request that set it.
    """

    user_id: str
    email: str
    email_key: str
    password_hash: str
    display_name: str
    created_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class Session:
    """Proof that someone logged in, and when it stops being proof.

    ``token_hash`` is stored, never the token. A leaked database must not hand
    over working sessions, and the server has no reason to be able to
    reconstruct one.
    """

    token_hash: str
    user_id: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class AudioRecord:
    """One generated segment, and the proof of what generated it."""

    cache_key: str
    document_id: str
    owner: str
    segment_id: str
    wav: bytes
    duration_seconds: float
    is_real_model: bool
    """False for the development tone.

    Served on every response so a placeholder can never be mistaken for
    narration, which CLAUDE.md requires and which no listener could check.
    """

    voice_id: str
    model_version: str


class Store(ABC):
    """Everything the API persists. A database implements this, not the routes."""

    @abstractmethod
    def put_document(self, document: Document) -> Document: ...

    @abstractmethod
    def get_document(self, document_id: str, owner: str) -> Document | None: ...

    @abstractmethod
    def list_documents(self, owner: str) -> list[Document]: ...

    @abstractmethod
    def delete_document(self, document_id: str, owner: str) -> bool: ...

    @abstractmethod
    def put_source(self, document_id: str, data: bytes) -> None: ...

    @abstractmethod
    def get_source(self, document_id: str) -> bytes | None: ...

    @abstractmethod
    def put_prepared(self, document_id: str, payload: str) -> None:
        """Keep the extracted pages and segments, as JSON.

        Derived data, but not cheap: about 30 seconds for a 168-page book. It
        used to live only in a dictionary inside the API process, which meant a
        restart left the document row saying "ready" and every page answering
        "not ready" — and meant preparation could never move to another process.
        """

    @abstractmethod
    def get_prepared(self, document_id: str) -> str | None: ...

    @abstractmethod
    def put_job(self, job: Job) -> Job: ...

    @abstractmethod
    def get_job(self, job_id: str, owner: str) -> Job | None: ...

    @abstractmethod
    def get_job_for_worker(self, job_id: str) -> Job | None:
        """A job without an owner check, for background work.

        Every other read is owner-scoped. This one cannot be: the worker running
        a job has no request and no caller, and the job itself is what records
        whose document it belongs to. Kept explicit and separately named so that
        an unscoped read is always a deliberate choice, never a forgotten
        argument.
        """

    @abstractmethod
    def jobs_for(self, document_id: str, owner: str) -> list[Job]: ...

    @abstractmethod
    def put_audio(self, record: AudioRecord) -> AudioRecord: ...

    @abstractmethod
    def get_audio(self, cache_key: str, owner: str) -> AudioRecord | None: ...

    @abstractmethod
    def put_progress(self, progress: Progress) -> Progress: ...

    @abstractmethod
    def get_progress(self, document_id: str, owner: str) -> Progress | None: ...

    # -- accounts ----------------------------------------------------------

    @abstractmethod
    def put_user(self, user: User) -> User:
        """Create a user. Raises :class:`EmailTaken` if the address is in use.

        Uniqueness is the store's job for the same reason ownership is: checking
        first and then inserting leaves a gap two simultaneous registrations can
        both pass through.
        """

    @abstractmethod
    def get_user(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_user_by_email(self, email_key: str) -> User | None: ...

    @abstractmethod
    def put_session(self, session: Session) -> Session: ...

    @abstractmethod
    def get_session(self, token_hash: str) -> Session | None:
        """The session for a token hash, or nothing. Expiry is not checked here.

        Deciding that a session has expired is the caller's job, in one place,
        so that "expired" and "never existed" cannot drift apart between
        implementations.
        """

    @abstractmethod
    def delete_session(self, token_hash: str) -> bool: ...

    @abstractmethod
    def delete_sessions_for_user(self, user_id: str) -> int:
        """Log a reader out everywhere. Returns how many sessions ended.

        Needed for a password change: a password that has been changed because
        it may be known to someone else has not been changed at all if their
        session keeps working.
        """


class InMemoryStore(Store):
    """A dictionary with a lock. Everything is lost when the process stops.

    Good enough to build and test the reader against, and honest about what it
    is: the health report says so, so nobody deploys it by accident.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._documents: dict[str, Document] = {}
        self._sources: dict[str, bytes] = {}
        self._prepared: dict[str, str] = {}
        self._jobs: dict[str, Job] = {}
        self._audio: dict[str, AudioRecord] = {}
        self._progress: dict[str, Progress] = {}
        self._users: dict[str, User] = {}
        self._users_by_email: dict[str, str] = {}
        self._sessions: dict[str, Session] = {}

    # -- documents ---------------------------------------------------------

    def put_document(self, document: Document) -> Document:
        with self._lock:
            self._documents[document.document_id] = document
        return document

    def get_document(self, document_id: str, owner: str) -> Document | None:
        with self._lock:
            document = self._documents.get(document_id)
        # Another owner's document is *absent*, not forbidden. See the module
        # docstring: a 403 on an existing id confirms that it exists.
        return document if document and document.owner == owner else None

    def list_documents(self, owner: str) -> list[Document]:
        with self._lock:
            return sorted(
                (d for d in self._documents.values() if d.owner == owner),
                key=lambda d: d.created_at,
                reverse=True,
            )

    def delete_document(self, document_id: str, owner: str) -> bool:
        """Remove the document and everything derived from it.

        CLAUDE.md requires deletion to remove derived text, audio and caches,
        not just the row that points at them. Anything left behind is private
        content that outlived the reader's decision to delete it.
        """
        with self._lock:
            document = self._documents.get(document_id)
            if document is None or document.owner != owner:
                return False
            del self._documents[document_id]
            self._sources.pop(document_id, None)
            self._prepared.pop(document_id, None)
            self._progress.pop(self._progress_key(document_id, owner), None)
            for job_id, job in list(self._jobs.items()):
                if job.document_id == document_id:
                    del self._jobs[job_id]
            for key, record in list(self._audio.items()):
                if record.document_id == document_id:
                    del self._audio[key]
            return True

    def put_source(self, document_id: str, data: bytes) -> None:
        with self._lock:
            self._sources[document_id] = data

    def get_source(self, document_id: str) -> bytes | None:
        with self._lock:
            return self._sources.get(document_id)

    def put_prepared(self, document_id: str, payload: str) -> None:
        with self._lock:
            self._prepared[document_id] = payload

    def get_prepared(self, document_id: str) -> str | None:
        with self._lock:
            return self._prepared.get(document_id)

    # -- jobs --------------------------------------------------------------

    def put_job(self, job: Job) -> Job:
        job = replace(job, updated_at=_now())
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str, owner: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        return job if job and job.owner == owner else None

    def get_job_for_worker(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs_for(self, document_id: str, owner: str) -> list[Job]:
        with self._lock:
            mine = [
                j for j in self._jobs.values() if j.document_id == document_id and j.owner == owner
            ]
        return sorted(mine, key=lambda j: j.created_at)

    # -- audio -------------------------------------------------------------

    def put_audio(self, record: AudioRecord) -> AudioRecord:
        with self._lock:
            self._audio[record.cache_key] = record
        return record

    def get_audio(self, cache_key: str, owner: str) -> AudioRecord | None:
        with self._lock:
            record = self._audio.get(cache_key)
        # Cached audio is still private content. CLAUDE.md: keep private audio
        # access-controlled even when it is cached.
        return record if record and record.owner == owner else None

    # -- progress ----------------------------------------------------------

    @staticmethod
    def _progress_key(document_id: str, owner: str) -> str:
        return f"{owner}:{document_id}"

    def put_progress(self, progress: Progress) -> Progress:
        with self._lock:
            self._progress[self._progress_key(progress.document_id, progress.owner)] = progress
        return progress

    def get_progress(self, document_id: str, owner: str) -> Progress | None:
        with self._lock:
            return self._progress.get(self._progress_key(document_id, owner))

    # -- accounts ----------------------------------------------------------

    def put_user(self, user: User) -> User:
        with self._lock:
            existing = self._users_by_email.get(user.email_key)
            if existing is not None and existing != user.user_id:
                raise EmailTaken(user.email_key)
            self._users[user.user_id] = user
            self._users_by_email[user.email_key] = user.user_id
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._lock:
            return self._users.get(user_id)

    def get_user_by_email(self, email_key: str) -> User | None:
        with self._lock:
            user_id = self._users_by_email.get(email_key)
            return self._users.get(user_id) if user_id else None

    def put_session(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.token_hash] = session
        return session

    def get_session(self, token_hash: str) -> Session | None:
        with self._lock:
            return self._sessions.get(token_hash)

    def delete_session(self, token_hash: str) -> bool:
        with self._lock:
            return self._sessions.pop(token_hash, None) is not None

    def delete_sessions_for_user(self, user_id: str) -> int:
        with self._lock:
            doomed = [h for h, s in self._sessions.items() if s.user_id == user_id]
            for token_hash in doomed:
                del self._sessions[token_hash]
            return len(doomed)


def build_store() -> Store:
    """Choose the store from configuration, once, at the composition root.

    Unset means in memory. That is the safe default rather than a timid one: a
    test run, a CI job and a ``--reload`` must not require a database server,
    and an in-memory store cannot quietly become production because
    ``GET /readiness`` reports it as a limitation on every call.

    A URL that is set but unreachable **stops the process**. The alternative is
    starting up on the in-memory store, accepting a reader's book, and losing it
    at the next restart while every health check said the deployment was
    configured for Postgres.
    """
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        return InMemoryStore()

    from .postgres import PostgresStore, migrate

    migrate(url)
    return PostgresStore(url)


def is_durable(store: Store) -> bool:
    """Does this store survive a restart?

    Asked by ``/readiness`` so the limitation is reported from what is actually
    running, rather than from what the configuration was meant to select.
    """
    return not isinstance(store, InMemoryStore)
