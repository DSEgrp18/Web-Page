"""Getting back into an account without email.

There is no email to send a reset link to, and a reader who has lost a
password must not lose their books with it. Registration hands over one
recovery code, once. Spending it sets a new password, ends every session, and
hands over a new code in its place.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_accounts import GOOD_PASSWORD, bearer, register

from sinhala_reader import Deps, create_app, passwords
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore

NEW_PASSWORD = "a-brand-new-password"


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


def recover(client: TestClient, code: str, email: str = "nimali@example.lk", password=NEW_PASSWORD):
    return client.post(
        "/auth/recover",
        json={"email": email, "recovery_code": code, "new_password": password},
    )


def login(client: TestClient, password: str, email: str = "nimali@example.lk"):
    return client.post("/auth/login", json={"email": email, "password": password})


class TestTheCodeIsHandedOverOnce:
    def test_at_registration(self, client: TestClient) -> None:
        body = register(client).json()

        assert [len(group) for group in body["recovery_code"].split("-")] == [4, 4, 4, 4]
        assert body["account"]["has_recovery_code"] is True

    def test_and_never_again(self, client: TestClient) -> None:
        token = register(client).json()["token"]

        assert "recovery_code" not in client.get("/auth/me", headers=bearer(token)).json()
        assert login(client, GOOD_PASSWORD).json()["recovery_code"] is None

    def test_only_its_hash_is_kept(self, client: TestClient, store: InMemoryStore) -> None:
        body = register(client).json()
        user = store.get_user(body["account"]["user_id"])

        assert user is not None and user.recovery_hash is not None
        assert body["recovery_code"] not in user.recovery_hash


class TestRecovering:
    def test_sets_a_new_password(self, client: TestClient) -> None:
        code = register(client).json()["recovery_code"]

        response = recover(client, code)

        assert response.status_code == 200
        assert login(client, NEW_PASSWORD).status_code == 200
        assert login(client, GOOD_PASSWORD).status_code == 401

    def test_ends_every_session(self, client: TestClient) -> None:
        """Whoever else had the account is signed out with the old password."""
        body = register(client).json()

        recover(client, body["recovery_code"])

        assert client.get("/auth/me", headers=bearer(body["token"])).status_code == 401

    def test_spends_the_code_and_hands_over_a_new_one(self, client: TestClient) -> None:
        old = register(client).json()["recovery_code"]

        new = recover(client, old).json()["recovery_code"]

        assert new and new != old
        assert recover(client, old, password="yet-another-password").status_code == 401
        assert recover(client, new, password="yet-another-password").status_code == 200

    def test_forgives_case_and_spacing(self, client: TestClient) -> None:
        code = register(client).json()["recovery_code"]

        response = recover(client, " " + code.lower().replace("-", " ") + " ")

        assert response.status_code == 200

    def test_is_audited(self, client: TestClient, store: InMemoryStore) -> None:
        body = register(client).json()

        recover(client, body["recovery_code"])

        kinds = [e.kind for e in store.audit_for(body["account"]["user_id"])]
        assert kinds == ["password_recovered"]


class TestWhatItRefusesToSay:
    def test_a_wrong_code_and_an_unknown_address_are_one_answer(self, client: TestClient) -> None:
        register(client)

        wrong = recover(client, "AAAA-BBBB-CCCC-DDDD")
        unknown = recover(client, "AAAA-BBBB-CCCC-DDDD", email="nobody@example.lk")

        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_an_account_with_no_code_gives_the_same_answer(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        user_id = register(client).json()["account"]["user_id"]
        store.set_recovery_hash(user_id, None)

        response = recover(client, "")

        assert response.status_code in (401, 422)
        assert login(client, GOOD_PASSWORD).status_code == 200

    def test_a_wrong_code_changes_nothing(self, client: TestClient) -> None:
        token = register(client).json()["token"]

        recover(client, "AAAA-BBBB-CCCC-DDDD")

        assert login(client, GOOD_PASSWORD).status_code == 200
        assert client.get("/auth/me", headers=bearer(token)).status_code == 200


class TestReplacingTheCode:
    def test_needs_the_password(self, client: TestClient) -> None:
        """A stolen session must not be able to mint a code and take the account."""
        token = register(client).json()["token"]

        response = client.post(
            "/auth/recovery-code",
            json={"current_password": "not-the-password"},
            headers=bearer(token),
        )

        assert response.status_code == 401

    def test_makes_the_old_one_useless(self, client: TestClient) -> None:
        body = register(client).json()

        replaced = client.post(
            "/auth/recovery-code",
            json={"current_password": GOOD_PASSWORD},
            headers=bearer(body["token"]),
        ).json()["recovery_code"]

        assert recover(client, body["recovery_code"]).status_code == 401
        assert recover(client, replaced).status_code == 200
