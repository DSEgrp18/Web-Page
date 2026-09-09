"""Test fixtures for the reader API.

Documents are built in memory by the worker's PDF fixture writer — the same one
its own tests use, and for the same reason: `scripts/verify-repo-hygiene.sh`
blocks `*.pdf` from ever being tracked.

Preparation runs inline rather than on a thread. A request and its work become
one step, so a failure surfaces as a failure instead of as a poll that
occasionally hasn't finished yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The worker's fixture writer lives in its tests directory, which is not a
# package. Adding it here keeps one PDF builder rather than two that drift.
_WORKER_TESTS = Path(__file__).resolve().parents[2] / "worker" / "tests"
if str(_WORKER_TESTS) not in sys.path:
    sys.path.insert(0, str(_WORKER_TESTS))

from pdf_fixtures import Page, Text, build_pdf, legacy_page, sinhala_page  # noqa: E402

from sinhala_reader import Deps, create_app  # noqa: E402
from sinhala_reader.security import AUTH_MODE_ENV, DEVELOPMENT_MODE  # noqa: E402

READER = "reader-one"
OTHER_READER = "reader-two"


@pytest.fixture(autouse=True)
def development_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API refuses to serve anything without this, by design."""
    monkeypatch.setenv(AUTH_MODE_ENV, DEVELOPMENT_MODE)


@pytest.fixture(autouse=True)
def clean_prepared_cache() -> None:
    from sinhala_reader import preparation

    preparation._PREPARED.clear()
    yield
    preparation._PREPARED.clear()


@pytest.fixture
def deps() -> Deps:
    return Deps(run_in_background=False)


@pytest.fixture
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def as_reader(client: TestClient, owner: str = READER) -> dict[str, str]:
    return {"X-Reader-User": owner}


def upload(client: TestClient, pdf: bytes, owner: str = READER, name: str = "book.pdf"):
    return client.post(
        "/documents",
        files={"file": (name, pdf, "application/pdf")},
        headers=as_reader(client, owner),
    )


@pytest.fixture
def book() -> bytes:
    """Two readable Sinhala pages."""
    return build_pdf([sinhala_page(), sinhala_page()])


@pytest.fixture
def prepared_document(client: TestClient, book: bytes):
    """An uploaded, successfully prepared document."""
    response = upload(client, book)
    assert response.status_code == 202, response.text
    return response.json()


__all__ = [
    "OTHER_READER",
    "READER",
    "Page",
    "Text",
    "as_reader",
    "build_pdf",
    "legacy_page",
    "sinhala_page",
    "upload",
]
