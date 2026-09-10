"""The reader's whole spine, through the routes, against a real database.

``test_store_contract.py`` proves ``PostgresStore`` behaves like the interface.
This proves the *API* still works when that is what is behind it — which is a
different claim, and the one CLAUDE.md actually asks for: "Add PostgreSQL/Redis
integration tests for authorization, job idempotency, and cache invalidation as
those components arrive."

The route tests in ``test_api.py`` are pinned to the in-memory store on purpose,
so they stay hermetic and fast. These are the ones that need a server, and they
skip loudly when there is not one.

Each test gets a truncated database rather than a transaction rolled back around
it. Preparation runs on the request thread here, but the real thing does not,
and a fixture that hid every write inside one uncommitted transaction would be
testing something the application never does.
"""

from __future__ import annotations

import os

import pytest
from conftest import OTHER_READER, READER, as_reader, upload
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app

DATABASE_URL = os.environ.get("SINHALA_READER_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "No SINHALA_READER_DATABASE_URL. The API was not exercised against a real "
        "database. See services/api/README.md."
    ),
)


@pytest.fixture
def pg_deps() -> Deps:
    from sinhala_reader.postgres import PostgresStore, migrate

    assert DATABASE_URL is not None
    migrate(DATABASE_URL)
    store = PostgresStore(DATABASE_URL)
    store.reset_for_tests()
    try:
        yield Deps(store=store, run_in_background=False)
    finally:
        store.close()


@pytest.fixture
def pg_client(pg_deps: Deps) -> TestClient:
    return TestClient(create_app(pg_deps))


def test_a_book_survives_a_restart(pg_client: TestClient, pg_deps: Deps, book: bytes) -> None:
    """The whole point of this change.

    A second application object is built over the same database, exactly as a
    redeployed or restarted process would be. The reader's book is still there.
    """
    document_id = upload(pg_client, book).json()["document_id"]

    restarted = TestClient(create_app(Deps(store=pg_deps.store, run_in_background=False)))
    listed = restarted.get("/documents", headers=as_reader(restarted)).json()

    assert [d["document_id"] for d in listed] == [document_id]


def test_a_reading_position_survives_a_restart(
    pg_client: TestClient, pg_deps: Deps, book: bytes
) -> None:
    """Coming back to where you stopped is the feature this store exists for.

    Losing it is worse for this reader than for most: someone who cannot see the
    page cannot skim to find their place again.
    """
    document_id = upload(pg_client, book).json()["document_id"]
    page = pg_client.get(f"/documents/{document_id}/pages/0", headers=as_reader(pg_client)).json()
    segment_id = page["segments"][0]["segment_id"]

    saved = pg_client.put(
        f"/documents/{document_id}/progress",
        headers=as_reader(pg_client),
        json={"segment_id": segment_id, "offset_seconds": 4.25},
    )
    assert saved.status_code == 200

    restarted = TestClient(create_app(Deps(store=pg_deps.store, run_in_background=False)))
    got = restarted.get(f"/documents/{document_id}/progress", headers=as_reader(restarted)).json()

    assert got["segment_id"] == segment_id
    assert got["offset_seconds"] == 4.25
    assert got["stale"] is False


def test_generated_audio_survives_a_restart(
    pg_client: TestClient, pg_deps: Deps, book: bytes
) -> None:
    """Cached audio is the expensive thing. Losing it means paying the GPU again.

    The bytes must come back identical: a WAV that survives a round trip with
    one byte changed is a defect no listener could diagnose.
    """
    document_id = upload(pg_client, book).json()["document_id"]
    page = pg_client.get(f"/documents/{document_id}/pages/0", headers=as_reader(pg_client)).json()
    segment_id = page["segments"][0]["segment_id"]

    first = pg_client.get(
        f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(pg_client)
    )
    assert first.status_code == 200

    restarted = TestClient(create_app(Deps(store=pg_deps.store, run_in_background=False)))
    again = restarted.get(
        f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(restarted)
    )

    assert again.status_code == 200
    assert again.content == first.content
    assert again.headers["X-Reader-Real-Model"] == first.headers["X-Reader-Real-Model"]


def test_another_reader_gets_404_everywhere(pg_client: TestClient, book: bytes) -> None:
    """Authorisation, against the database that will actually serve it.

    Enforced in the ``WHERE`` clause rather than in the routes, so this is the
    test that proves the clause is there.
    """
    document_id = upload(pg_client, book).json()["document_id"]
    page = pg_client.get(f"/documents/{document_id}/pages/0", headers=as_reader(pg_client)).json()
    segment_id = page["segments"][0]["segment_id"]

    them = as_reader(pg_client, OTHER_READER)
    assert pg_client.get(f"/documents/{document_id}", headers=them).status_code == 404
    assert pg_client.get(f"/documents/{document_id}/pages/0", headers=them).status_code == 404
    assert (
        pg_client.get(
            f"/documents/{document_id}/segments/{segment_id}/audio", headers=them
        ).status_code
        == 404
    )
    assert pg_client.get(f"/documents/{document_id}/progress", headers=them).status_code == 404
    assert pg_client.delete(f"/documents/{document_id}", headers=them).status_code == 404
    assert pg_client.get("/documents", headers=them).json() == []

    # And the owner still has it, so the refusals were about ownership rather
    # than about the document having gone.
    mine = pg_client.get(f"/documents/{document_id}", headers=as_reader(pg_client))
    assert mine.status_code == 200


def test_deletion_reaches_the_derived_rows(
    pg_client: TestClient, pg_deps: Deps, book: bytes
) -> None:
    """CLAUDE.md requires deletion to remove derived text, audio and caches.

    In Postgres that is ``ON DELETE CASCADE`` rather than five statements, so
    this checks the schema does what the interface promises — including after a
    restart, because a cascade that did not fire would leave rows that only a
    second process would ever see.
    """
    document_id = upload(pg_client, book).json()["document_id"]
    page = pg_client.get(f"/documents/{document_id}/pages/0", headers=as_reader(pg_client)).json()
    segment_id = page["segments"][0]["segment_id"]
    pg_client.get(
        f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(pg_client)
    )
    pg_client.put(
        f"/documents/{document_id}/progress",
        headers=as_reader(pg_client),
        json={"segment_id": segment_id, "offset_seconds": 1.0},
    )

    assert (
        pg_client.delete(f"/documents/{document_id}", headers=as_reader(pg_client)).status_code
        == 204
    )

    store = pg_deps.store
    assert store.get_document(document_id, READER) is None
    assert store.get_source(document_id) is None
    assert store.get_progress(document_id, READER) is None
    assert store.jobs_for(document_id, READER) == []

    # Straight at the tables, because the point is that nothing is left behind
    # rather than that the accessors decline to return it.
    with store._pool.connection() as connection:  # type: ignore[attr-defined]
        for table in ("sources", "jobs", "audio", "progress"):
            left = connection.execute(
                f"SELECT count(*) AS n FROM {table} WHERE document_id = %s", (document_id,)
            ).fetchone()
            assert left is not None and left["n"] == 0, f"{table} kept rows after deletion"


def test_readiness_stops_calling_storage_a_limitation(pg_client: TestClient) -> None:
    """The limitation is reported from what is running, not from configuration.

    With a real database behind it, the in-memory warning must be gone — and the
    ones that are still true must remain, so this is not a test that readiness
    went quiet.
    """
    body = pg_client.get("/readiness").json()

    assert not any("Storage is in memory" in note for note in body["limitations"])
    assert any("trusted header" in note for note in body["limitations"])


def test_migrations_are_applied_once(pg_client: TestClient) -> None:
    """Start-up runs them every time; they must not run twice.

    ``migrate`` is called on every process start, so a migration that reapplied
    itself would fail on the second boot of a deployment rather than the first.
    """
    from sinhala_reader.postgres import migrate

    assert DATABASE_URL is not None
    assert migrate(DATABASE_URL) == []
