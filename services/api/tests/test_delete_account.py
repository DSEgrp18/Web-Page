"""Deleting an account deletes everything in it.

CLAUDE.md: deletion removes derived text, embeddings, audio and caches. For an
account that means every book, each with everything derived from it, then the
account itself, its sessions and its history.
"""

from __future__ import annotations

import pytest
from conftest import build_pdf, sinhala_page
from fastapi.testclient import TestClient
from test_accounts import GOOD_PASSWORD, bearer, register

from sinhala_reader import Deps, create_app, passwords, preparation
from sinhala_reader.security import AUTH_MODE_ENV, CSRF_HEADER
from sinhala_reader.storage import InMemoryStore


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "SCRYPT_LOG_N", 8)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    import sinhala_reader.accounts as accounts

    monkeypatch.setattr(accounts, "_ABSENT_ACCOUNT_HASH", None)


@pytest.fixture(autouse=True)
def sessions_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_MODE_ENV, "sessions")


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def client(store: InMemoryStore) -> TestClient:
    return TestClient(
        create_app(Deps(store=store, run_in_background=False, warm_on_start=False)),
        headers={"X-Session-Transport": "bearer"},
    )


def _with_a_book(client: TestClient, email: str = "nimali@example.lk") -> tuple[str, str, str]:
    body = register(client, email=email).json()
    token = body["token"]
    document_id = client.post(
        "/documents",
        files={"file": ("book.pdf", build_pdf([sinhala_page()]), "application/pdf")},
        headers=bearer(token),
    ).json()["document_id"]
    return token, body["account"]["user_id"], document_id


def _delete(client: TestClient, token: str, password: str = GOOD_PASSWORD):
    return client.request(
        "DELETE", "/auth/account", json={"current_password": password}, headers=bearer(token)
    )


class TestDeletingAnAccount:
    def test_removes_every_book_and_what_was_made_from_it(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, user_id, document_id = _with_a_book(client)
        client.post(
            f"/documents/{document_id}/bookmarks",
            json={"segment_id": "0000-s0"},
            headers=bearer(token),
        )
        assert store.get_prepared(document_id) is not None

        response = _delete(client, token)

        assert response.status_code == 204
        assert store.list_documents(user_id) == []
        assert store.get_source(document_id) is None
        assert store.get_prepared(document_id) is None
        assert store.jobs_for(document_id, user_id) == []
        assert document_id not in preparation._PREPARED

    def test_removes_the_account_its_sessions_and_its_history(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, user_id, _ = _with_a_book(client)

        _delete(client, token)

        assert store.get_user(user_id) is None
        assert store.audit_for(user_id) == []
        assert client.get("/auth/me", headers=bearer(token)).status_code == 401
        signing_in = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD}
        )
        assert signing_in.status_code == 401

    def test_the_address_can_be_used_again(self, client: TestClient) -> None:
        token, _, _ = _with_a_book(client)
        _delete(client, token)

        assert register(client).status_code == 201

    def test_needs_the_password(self, client: TestClient, store: InMemoryStore) -> None:
        """An open session on a shared phone must not be enough."""
        token, user_id, document_id = _with_a_book(client)

        response = _delete(client, token, password="not-the-password")

        assert response.status_code == 401
        assert store.get_user(user_id) is not None
        assert store.get_source(document_id) is not None

    def test_leaves_other_readers_alone(self, client: TestClient, store: InMemoryStore) -> None:
        mine, _, _ = _with_a_book(client, "one@example.lk")
        theirs, their_id, their_book = _with_a_book(client, "two@example.lk")

        _delete(client, mine)

        assert store.get_user(their_id) is not None
        assert store.get_source(their_book) is not None
        assert client.get("/auth/me", headers=bearer(theirs)).status_code == 200


class TestFromABrowser:
    def test_needs_the_csrf_token_and_clears_the_cookie(self, store: InMemoryStore) -> None:
        browser = TestClient(
            create_app(Deps(store=store, run_in_background=False, warm_on_start=False)),
            base_url="https://testserver",
        )
        csrf = browser.post(
            "/auth/register",
            json={"email": "nimali@example.lk", "password": GOOD_PASSWORD, "display_name": "N"},
        ).json()["csrf_token"]
        body = {"current_password": GOOD_PASSWORD}

        refused = browser.request("DELETE", "/auth/account", json=body)
        deleted = browser.request("DELETE", "/auth/account", json=body, headers={CSRF_HEADER: csrf})

        assert refused.status_code == 403
        assert deleted.status_code == 204
        assert "max-age=0" in deleted.headers["set-cookie"].lower()
