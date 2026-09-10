"""Signing in, and everything the API refuses to say while doing it.

Most of these are about **absence**: that a failure does not reveal whether an
account exists, that a token never appears where it could be logged, that the
development header stops working the moment real accounts are on.

That emphasis is not generic security hygiene. This service is for blind and
low-vision readers and students, so knowing that an address has an account here
is knowing something about a person's disability. A login that distinguishes
"no such account" from "wrong password" publishes that, one address at a time.
"""

from __future__ import annotations

import pytest
from conftest import as_reader
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app, passwords
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore

GOOD_PASSWORD = "a-long-enough-password"


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash cheaply, because the real cost is half a second per call.

    Patched rather than configured through the environment: a setting that
    weakens password hashing is one typo away from a database of cheap hashes.
    ``/readiness`` reports when this has happened, and one test below checks
    that it does.
    """
    monkeypatch.setattr(passwords, "SCRYPT_LOG_N", 8)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    monkeypatch.setattr(passwords, "_ABSENT_ACCOUNT_HASH", None, raising=False)
    import sinhala_reader.accounts as accounts

    monkeypatch.setattr(accounts, "_ABSENT_ACCOUNT_HASH", None)


@pytest.fixture(autouse=True)
def sessions_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_MODE_ENV, "sessions")


@pytest.fixture
def client() -> TestClient:
    return TestClient(
        create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
    )


def register(
    client: TestClient,
    email: str = "nimali@example.lk",
    password: str = GOOD_PASSWORD,
    name: str = "Nimali",
):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRegistering:
    def test_creates_an_account_and_signs_in(self, client: TestClient) -> None:
        """Signed in immediately, because retyping a password just chosen is a
        real cost on a screen reader and buys nothing."""
        response = register(client)

        assert response.status_code == 201
        body = response.json()
        assert body["token"]
        assert body["account"]["display_name"] == "Nimali"
        assert client.get("/auth/me", headers=bearer(body["token"])).status_code == 200

    def test_the_address_is_kept_as_it_was_typed(self, client: TestClient) -> None:
        """A name is theirs to capitalise; showing it back changed is a small unkindness."""
        response = register(client, email="Nimali@Example.LK")

        assert response.json()["account"]["email"] == "Nimali@Example.LK"

    def test_but_matching_ignores_case(self, client: TestClient) -> None:
        register(client, email="Nimali@Example.LK")

        clash = register(client, email="nimali@example.lk")
        assert clash.status_code == 409

        signed_in = client.post(
            "/auth/login", json={"email": "NIMALI@EXAMPLE.LK", "password": GOOD_PASSWORD}
        )
        assert signed_in.status_code == 200

    def test_a_short_password_is_refused_with_the_reason(self, client: TestClient) -> None:
        """The one refusal that must be specific: the reader has to know what to fix."""
        response = register(client, password="short")

        assert response.status_code == 422
        assert str(passwords.MIN_LENGTH) in response.text

    @pytest.mark.parametrize(
        "address", ["nimali", "nimali@", "@example.lk", "nimali example@lk", "a@b"]
    )
    def test_something_that_is_not_an_address_is_refused(
        self, client: TestClient, address: str
    ) -> None:
        assert register(client, email=address).status_code == 422

    def test_no_password_or_hash_is_ever_returned(self, client: TestClient) -> None:
        body = register(client).text

        assert GOOD_PASSWORD not in body
        assert "scrypt" not in body
        assert "password" not in body


class TestSigningIn:
    def test_the_right_password_works(self, client: TestClient) -> None:
        register(client)

        response = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["token"]

    def test_a_wrong_password_and_a_missing_account_are_indistinguishable(
        self, client: TestClient
    ) -> None:
        """The central property of this module.

        Same status, same body. Anything else enumerates the readers of a
        service for people with disabilities.
        """
        register(client)

        wrong = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": "not-the-password"}
        )
        absent = client.post(
            "/auth/login", json={"email": "nobody@example.lk", "password": "not-the-password"}
        )

        assert wrong.status_code == absent.status_code == 401
        assert wrong.json() == absent.json()

    def test_a_missing_account_still_pays_for_a_password_check(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Timing is the leak; this tests the mechanism that closes it.

        Without the dummy verification in ``accounts.login``, a missing account
        skips scrypt entirely and answers sooner — which says "no account here"
        in milliseconds, whatever the body says.

        Asserting on elapsed time was tried first and was worthless: these tests
        lower the scrypt cost, so both paths finish too fast to tell apart, and
        the assertion passed happily with the leak reintroduced. Counting the
        verifications is exact, fast, and cannot be fooled by a slow runner.
        """
        register(client)
        calls: list[str] = []
        real = passwords.verify

        def counted(password: str, stored: str) -> tuple[bool, bool]:
            calls.append(stored)
            return real(password, stored)

        monkeypatch.setattr(passwords, "verify", counted)

        client.post(
            "/auth/login", json={"email": "nobody@example.lk", "password": "not-the-password"}
        )

        assert len(calls) == 1, "a login for an unknown address must still verify a hash"
        assert calls[0].startswith("scrypt$"), "and it must be a real hash, not a placeholder"

    def test_each_sign_in_gets_its_own_token(self, client: TestClient) -> None:
        first = register(client).json()["token"]
        second = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD}
        ).json()["token"]

        assert first != second
        # And the earlier one still works: signing in on a phone must not sign
        # you out on a laptop mid-chapter.
        assert client.get("/auth/me", headers=bearer(first)).status_code == 200


class TestTheTokenItself:
    def test_a_token_that_was_never_issued_is_refused(self, client: TestClient) -> None:
        assert client.get("/auth/me", headers=bearer("not-a-real-token")).status_code == 401

    def test_a_missing_header_is_refused_and_names_the_scheme(self, client: TestClient) -> None:
        response = client.get("/auth/me")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "abc"])
    def test_a_malformed_authorization_header_is_refused(
        self, client: TestClient, header: str
    ) -> None:
        assert client.get("/auth/me", headers={"Authorization": header}).status_code == 401

    def test_the_scheme_is_case_insensitive(self, client: TestClient) -> None:
        """RFC 7235 says it is, and refusing a reader over capitalisation is petty."""
        token = register(client).json()["token"]

        lowercase = client.get("/auth/me", headers={"Authorization": f"bearer {token}"})
        assert lowercase.status_code == 200

    def test_an_expired_session_is_refused_and_removed(self, client: TestClient) -> None:
        from datetime import UTC, datetime, timedelta

        from sinhala_reader import sessions

        token = register(client).json()["token"]
        store = client.app.state.deps.store
        stale = store.get_session(sessions.token_hash(token))
        gone = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        store.put_session(
            type(stale)(
                token_hash=stale.token_hash,
                user_id=stale.user_id,
                created_at=stale.created_at,
                expires_at=gone,
            )
        )

        assert client.get("/auth/me", headers=bearer(token)).status_code == 401
        # Removed, not merely refused: a dead credential left in the database is
        # one clock error away from working again.
        assert store.get_session(sessions.token_hash(token)) is None


class TestSigningOut:
    def test_ends_the_session(self, client: TestClient) -> None:
        token = register(client).json()["token"]

        assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
        assert client.get("/auth/me", headers=bearer(token)).status_code == 401

    def test_is_calm_when_there_was_nothing_to_end(self, client: TestClient) -> None:
        """Pressing it twice, or after expiry, must give the same answer.

        It also must not become a way to find out whether a token is live.
        """
        assert client.post("/auth/logout").status_code == 204
        assert client.post("/auth/logout", headers=bearer("never-issued")).status_code == 204


class TestChangingAPassword:
    def test_works_and_ends_every_session(self, client: TestClient) -> None:
        """The point of ending them.

        A password changed because someone else may know it has not been
        changed at all if their session keeps working.
        """
        phone = register(client).json()["token"]
        laptop = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD}
        ).json()["token"]

        changed = client.post(
            "/auth/password",
            headers=bearer(phone),
            json={"current_password": GOOD_PASSWORD, "new_password": "a-different-password"},
        )

        assert changed.status_code == 204
        assert client.get("/auth/me", headers=bearer(phone)).status_code == 401
        assert client.get("/auth/me", headers=bearer(laptop)).status_code == 401
        assert (
            client.post(
                "/auth/login",
                json={"email": "nimali@example.lk", "password": "a-different-password"},
            ).status_code
            == 200
        )

    def test_the_current_password_is_required(self, client: TestClient) -> None:
        """Because a session might be stolen.

        Without this, whoever holds the token locks the reader out of their own
        account.
        """
        token = register(client).json()["token"]

        response = client.post(
            "/auth/password",
            headers=bearer(token),
            json={"current_password": "not-the-password", "new_password": "a-different-password"},
        )

        assert response.status_code == 401
        assert client.get("/auth/me", headers=bearer(token)).status_code == 200

    def test_a_weak_new_password_is_refused(self, client: TestClient) -> None:
        token = register(client).json()["token"]

        response = client.post(
            "/auth/password",
            headers=bearer(token),
            json={"current_password": GOOD_PASSWORD, "new_password": "short"},
        )

        assert response.status_code == 422


class TestTheDevelopmentHeaderIsOffWhenAccountsAreOn:
    def test_the_header_no_longer_identifies_anyone(self, client: TestClient) -> None:
        """The check that matters most in this file.

        If both schemes were accepted at once, every account would be bypassable
        by typing a user id into a header, and nothing would look wrong.
        """
        token = register(client).json()["token"]
        owner = client.get("/auth/me", headers=bearer(token)).json()["user_id"]

        assert client.get("/documents", headers={"X-Reader-User": owner}).status_code == 401

    def test_documents_need_a_token(self, client: TestClient) -> None:
        token = register(client).json()["token"]

        assert client.get("/documents").status_code == 401
        assert client.get("/documents", headers=bearer(token)).status_code == 200


class TestWhenAccountsAreOff:
    def test_the_account_routes_say_which_setting_turns_them_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 503 naming the setting beats a 404 that looks like a missing feature."""
        monkeypatch.setenv(AUTH_MODE_ENV, "development")
        client = TestClient(
            create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
        )

        response = register(client)

        assert response.status_code == 503
        assert AUTH_MODE_ENV in response.text

    def test_the_header_still_works_in_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV, "development")
        client = TestClient(
            create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
        )

        assert client.get("/documents", headers=as_reader(client)).status_code == 200

    def test_nothing_is_served_with_no_mode_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(AUTH_MODE_ENV, raising=False)
        client = TestClient(
            create_app(Deps(store=InMemoryStore(), run_in_background=False, warm_on_start=False))
        )

        assert client.get("/documents", headers=as_reader(client)).status_code == 503


class TestReadinessKeepsTellingTheTruth:
    def test_it_names_what_accounts_still_lack(self, client: TestClient) -> None:
        """ "We have logins" must not be allowed to stand in for "this is safe"."""
        limitations = client.get("/readiness").json()["limitations"]

        assert any("rate limiting" in note for note in limitations)
        assert any("password reset" in note for note in limitations)
        # And the header warning is gone, because the header no longer works.
        assert not any("trusted header" in note for note in limitations)

    def test_it_reports_cheap_hashing(self, client: TestClient) -> None:
        """This suite lowers the cost. A server that somehow ran this way must say so."""
        limitations = client.get("/readiness").json()["limitations"]

        assert any("hashed more cheaply" in note for note in limitations)
