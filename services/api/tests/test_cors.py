"""Whether a browser may talk to this API at all.

The reader interface runs on its own origin, so this is not a detail: without
it the browser refuses every request before sending it, and the interface can
only tell a blind reader that the server is unreachable. With it configured too
loosely, any page on the web can read a student's private textbook, because the
identity is a header anyone can send.

So both directions are tested: that the named origin works, and that nothing
else does.

The store is named rather than taken from the environment: with
``SINHALA_READER_DATABASE_URL`` set, these would otherwise share a database with
every other test.
"""

from __future__ import annotations

import pytest
from conftest import READER, as_reader
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app
from sinhala_reader.app import REAL_MODEL_HEADER
from sinhala_reader.security import ORIGINS_ENV
from sinhala_reader.storage import InMemoryStore

READER_UI = "http://localhost:3000"
READER_HEADER_NAME = "x-reader-user"


def app_with_origins(monkeypatch: pytest.MonkeyPatch, value: str | None) -> TestClient:
    if value is None:
        monkeypatch.delenv(ORIGINS_ENV, raising=False)
    else:
        monkeypatch.setenv(ORIGINS_ENV, value)
    # The middleware is chosen when the app is built, so the environment has to
    # be set first — the same way a deployment does it.
    return TestClient(create_app(Deps(store=InMemoryStore(), run_in_background=False)))


def test_no_origin_configured_means_no_browser_may_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = app_with_origins(monkeypatch, None)
    response = client.get("/documents", headers={**as_reader(client, READER), "Origin": READER_UI})
    # The request itself succeeds — this is a server, not a firewall — but the
    # browser will discard the response because it is not allowed to be read.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_a_named_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = app_with_origins(monkeypatch, READER_UI)
    response = client.get("/documents", headers={**as_reader(client, READER), "Origin": READER_UI})
    assert response.headers["access-control-allow-origin"] == READER_UI


def test_another_origin_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    client = app_with_origins(monkeypatch, READER_UI)
    response = client.get(
        "/documents",
        headers={**as_reader(client, READER), "Origin": "https://not-the-reader.example"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_the_placeholder_header_survives_the_crossing(monkeypatch: pytest.MonkeyPatch) -> None:
    """`X-Reader-Real-Model` is useless if the browser is not allowed to read it.

    Cross-origin JavaScript sees only a short list of response headers unless
    the server names the others. If this one is missed, the reader hears a tone
    and the interface has no way to know it was not speech.
    """
    client = app_with_origins(monkeypatch, READER_UI)
    # The list travels on the real response, not on the preflight.
    response = client.get("/documents", headers={**as_reader(client, READER), "Origin": READER_UI})
    exposed = response.headers.get("access-control-expose-headers", "")
    assert REAL_MODEL_HEADER.lower() in exposed.lower()


def test_the_identity_header_is_allowed_through_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = app_with_origins(monkeypatch, READER_UI)
    preflight = client.options(
        "/documents",
        headers={
            "Origin": READER_UI,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-reader-user,content-type",
        },
    )
    assert preflight.status_code == 200
    allowed = preflight.headers["access-control-allow-headers"].lower()
    assert "x-reader-user" in allowed


def test_readiness_says_when_no_browser_can_reach_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client = app_with_origins(monkeypatch, None)
    limitations = client.get("/readiness").json()["limitations"]
    assert any(ORIGINS_ENV in note for note in limitations)


def test_readiness_says_when_any_website_can(monkeypatch: pytest.MonkeyPatch) -> None:
    client = app_with_origins(monkeypatch, "*")
    limitations = client.get("/readiness").json()["limitations"]
    # A wildcard plus header identity means any page can read any reader's
    # documents. That must be stated, not left to be discovered.
    assert any("Any website" in note for note in limitations)


def test_the_browser_may_send_a_range_and_read_what_came_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial PDF reads are cross-origin, so both halves need CORS.

    The preflight has to allow `Range`, or pdf.js never sends one and falls
    back to downloading whole books. And `Content-Range` has to be exposed, or
    the response header exists on the wire but not to the page, and pdf.js
    cannot tell which bytes it received.
    """
    client = app_with_origins(monkeypatch, READER_UI)
    preflight = client.options(
        "/documents/doc_1/file",
        headers={
            "Origin": READER_UI,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "range",
        },
    )
    assert preflight.status_code == 200
    assert "range" in preflight.headers["access-control-allow-headers"].lower()

    exposed = client.get("/readiness", headers={"Origin": READER_UI}).headers[
        "access-control-expose-headers"
    ]
    assert "Content-Range" in exposed
    assert "Accept-Ranges" in exposed


def test_a_book_can_be_renamed_from_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH is not in the CORS default set, and renaming is a PATCH."""
    client = app_with_origins(monkeypatch, READER_UI)
    preflight = client.options(
        "/documents/doc_1",
        headers={
            "Origin": READER_UI,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type," + READER_HEADER_NAME,
        },
    )
    assert preflight.status_code == 200
    assert "PATCH" in preflight.headers["access-control-allow-methods"]
