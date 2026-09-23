"""A browser's session: an httpOnly cookie, and proof each request is ours.

What a browser gets is a cookie no script can read. Because the browser sends
that cookie whoever asks, a cookie-authenticated request must also show it
came from this site: Fetch Metadata on every request, and a CSRF token on
every change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import build_pdf, sinhala_page
from fastapi.testclient import TestClient
from test_accounts import GOOD_PASSWORD

from sinhala_reader import Deps, create_app, passwords, sessions
from sinhala_reader.security import (
    AUTH_MODE_ENV,
    CSRF_HEADER,
    SECRET_ENV,
    SESSION_COOKIE,
    csrf_token,
)
from sinhala_reader.storage import InMemoryStore, Session


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


def browser(store: InMemoryStore) -> TestClient:
    """A client that behaves like a page: https, cookies, no bearer token."""
    app = create_app(Deps(store=store, run_in_background=False, warm_on_start=False))
    return TestClient(app, base_url="https://testserver")


def signed_up(client: TestClient, email: str = "nimali@example.lk") -> str:
    """Register in this browser. Returns the CSRF token the page is given."""
    response = client.post(
        "/auth/register",
        json={"email": email, "password": GOOD_PASSWORD, "display_name": "Nimali"},
    )
    assert response.status_code == 201, response.text
    return response.json()["csrf_token"]


def upload(client: TestClient, csrf: str | None, **headers: str):
    sent = {CSRF_HEADER: csrf} if csrf is not None else {}
    sent.update(headers)
    return client.post(
        "/documents",
        files={"file": ("book.pdf", build_pdf([sinhala_page()]), "application/pdf")},
        headers=sent,
    )


class TestTheCookie:
    def test_a_browser_gets_a_cookie_and_no_token(self, store: InMemoryStore) -> None:
        client = browser(store)
        response = client.post(
            "/auth/register",
            json={"email": "nimali@example.lk", "password": GOOD_PASSWORD, "display_name": "N"},
        )

        assert response.json()["token"] is None
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}=")
        for attribute in ("HttpOnly", "Secure", "Path=/", "SameSite=lax"):
            assert attribute.lower() in cookie.lower()
        assert "domain=" not in cookie.lower()

    def test_it_signs_the_browser_in(self, store: InMemoryStore) -> None:
        client = browser(store)
        signed_up(client)

        me = client.get("/auth/me")

        assert me.status_code == 200
        assert me.json()["email"] == "nimali@example.lk"

    def test_me_gives_a_reloaded_page_its_csrf_token(self, store: InMemoryStore) -> None:
        client = browser(store)
        at_sign_up = signed_up(client)

        assert client.get("/auth/me").json()["csrf_token"] == at_sign_up

    def test_a_bearer_client_can_still_ask_for_a_token(self, store: InMemoryStore) -> None:
        client = browser(store)
        response = client.post(
            "/auth/register",
            json={"email": "a@example.lk", "password": GOOD_PASSWORD, "display_name": "A"},
            headers={"X-Session-Transport": "bearer"},
        )

        assert response.json()["token"]
        assert "set-cookie" not in response.headers


class TestCsrf:
    def test_a_change_without_the_token_is_refused(self, store: InMemoryStore) -> None:
        client = browser(store)
        signed_up(client)

        assert upload(client, None).status_code == 403
        assert upload(client, "not-the-token").status_code == 403
        assert store.list_documents(client.get("/auth/me").json()["user_id"]) == []

    def test_with_the_token_it_goes_through(self, store: InMemoryStore) -> None:
        client = browser(store)
        csrf = signed_up(client)

        assert upload(client, csrf).status_code == 202

    def test_reading_needs_no_token(self, store: InMemoryStore) -> None:
        client = browser(store)
        signed_up(client)

        assert client.get("/documents").status_code == 200

    def test_one_sessions_token_does_not_work_for_another(self, store: InMemoryStore) -> None:
        mine, theirs = browser(store), browser(store)
        signed_up(mine, "one@example.lk")
        their_csrf = signed_up(theirs, "two@example.lk")

        assert upload(mine, their_csrf).status_code == 403

    def test_the_token_is_an_hmac_of_the_session(self, store: InMemoryStore) -> None:
        client = browser(store)
        csrf = signed_up(client)
        token = client.cookies.get(SESSION_COOKIE)

        assert token is not None
        assert csrf == csrf_token(sessions.token_hash(token))
        assert token not in csrf


class TestFetchMetadata:
    @pytest.mark.parametrize("site", ["cross-site", "same-site"])
    def test_another_sites_request_is_refused_even_to_read(
        self, store: InMemoryStore, site: str
    ) -> None:
        """GET too: asking for audio starts synthesis, which costs money."""
        client = browser(store)
        signed_up(client)

        assert client.get("/documents", headers={"Sec-Fetch-Site": site}).status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "none"])
    def test_this_site_and_a_typed_address_are_allowed(
        self, store: InMemoryStore, site: str
    ) -> None:
        client = browser(store)
        signed_up(client)

        assert client.get("/documents", headers={"Sec-Fetch-Site": site}).status_code == 200

    def test_another_site_cannot_sign_a_reader_in(self, store: InMemoryStore) -> None:
        """Login CSRF: a page signing the reader into an account it controls."""
        client = browser(store)
        signed_up(client)
        client.post("/auth/logout", headers={"Sec-Fetch-Site": "same-origin"})

        response = client.post(
            "/auth/login",
            json={"email": "nimali@example.lk", "password": GOOD_PASSWORD},
            headers={"Sec-Fetch-Site": "cross-site"},
        )

        assert response.status_code == 403
        assert "set-cookie" not in response.headers


class TestSigningOut:
    def test_ends_the_session_and_clears_the_cookie(self, store: InMemoryStore) -> None:
        client = browser(store)
        signed_up(client)
        token = client.cookies.get(SESSION_COOKIE)

        response = client.post("/auth/logout")

        assert response.status_code == 204
        assert SESSION_COOKIE in response.headers["set-cookie"]
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert store.get_session(sessions.token_hash(token)) is None
        assert client.get("/auth/me").status_code == 401

    def test_everywhere_ends_every_device(self, store: InMemoryStore) -> None:
        phone, laptop = browser(store), browser(store)
        csrf = signed_up(phone)
        laptop.post("/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD})
        assert laptop.get("/auth/me").status_code == 200

        response = phone.post("/auth/logout-everywhere", headers={CSRF_HEADER: csrf})

        assert response.status_code == 204
        assert laptop.get("/auth/me").status_code == 401
        assert phone.get("/auth/me").status_code == 401

    def test_everywhere_needs_the_csrf_token(self, store: InMemoryStore) -> None:
        phone = browser(store)
        signed_up(phone)

        assert phone.post("/auth/logout-everywhere").status_code == 403
        assert phone.get("/auth/me").status_code == 200


class TestTwoReaders:
    def test_a_cookie_reaches_only_its_own_books(self, store: InMemoryStore) -> None:
        """The ownership rule, through cookies: another reader's book is absent."""
        mine, theirs = browser(store), browser(store)
        csrf = signed_up(mine, "one@example.lk")
        signed_up(theirs, "two@example.lk")
        document_id = upload(mine, csrf).json()["document_id"]

        assert theirs.get(f"/documents/{document_id}").status_code == 404
        assert theirs.get("/documents").json() == []
        assert mine.get(f"/documents/{document_id}").status_code == 200


class TestRenewal:
    def test_a_renewed_session_renews_the_cookie(self, store: InMemoryStore) -> None:
        """Or the browser drops the cookie while the server still honours it."""
        client = browser(store)
        signed_up(client)
        token = client.cookies.get(SESSION_COOKIE)
        stored = store.get_session(sessions.token_hash(token))
        old = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        store.put_session(
            Session(
                token_hash=stored.token_hash,
                user_id=stored.user_id,
                created_at=stored.created_at,
                expires_at=old,
            )
        )

        response = client.get("/documents")

        assert response.status_code == 200
        assert SESSION_COOKIE in response.headers.get("set-cookie", "")
        assert store.get_session(sessions.token_hash(token)).expires_at > old

    def test_a_fresh_session_sets_nothing(self, store: InMemoryStore) -> None:
        client = browser(store)
        signed_up(client)

        assert "set-cookie" not in client.get("/documents").headers


class TestTheSecret:
    @pytest.mark.parametrize("secret", [None, "too-short"])
    def test_sessions_do_not_start_without_one(
        self, monkeypatch: pytest.MonkeyPatch, secret: str | None
    ) -> None:
        if secret is None:
            monkeypatch.delenv(SECRET_ENV, raising=False)
        else:
            monkeypatch.setenv(SECRET_ENV, secret)

        with pytest.raises(ValueError, match=SECRET_ENV):
            create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))

    def test_development_mode_does_not_need_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV, "development")
        monkeypatch.delenv(SECRET_ENV, raising=False)

        create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
