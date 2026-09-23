"""Roles: nobody can make themselves a teacher.

Registration makes a student. A teacher is made on the admin command line, or
by a single-use invitation an admin printed there. Every grant is audited, and
a whole-account write never changes a role, so a stale copy saved after a
password change cannot quietly demote a teacher.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_accounts import GOOD_PASSWORD, bearer, register

from sinhala_reader import Deps, admin, codes, create_app, passwords
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore, Role, TeacherInvite


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
    return TestClient(create_app(Deps(store=store, run_in_background=False, warm_on_start=False)))


def _invite(store: InMemoryStore, *, days: int = 7, code: str | None = None) -> str:
    code = code or codes.new_code()
    now = datetime.now(UTC)
    store.put_invite(
        TeacherInvite(
            code_hash=codes.code_hash(code),
            created_by="cli",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=days)).isoformat(),
        )
    )
    return code


def _signed_in(client: TestClient, email: str = "nimali@example.lk") -> tuple[str, str]:
    body = register(client, email=email).json()
    return body["token"], body["account"]["user_id"]


class TestRegistration:
    def test_always_makes_a_student(self, client: TestClient) -> None:
        body = register(client).json()
        assert body["account"]["role"] == "student"

    def test_a_role_in_the_request_is_ignored(self, client: TestClient) -> None:
        """Nobody can declare themselves a teacher."""
        response = client.post(
            "/auth/register",
            json={
                "email": "a@example.lk",
                "password": GOOD_PASSWORD,
                "display_name": "A",
                "role": "teacher",
            },
        )
        assert response.json()["account"]["role"] == "student"


class TestInvitations:
    def test_a_student_becomes_a_teacher_with_one(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, user_id = _signed_in(client)
        code = _invite(store)

        response = client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(token))

        assert response.status_code == 200
        assert response.json()["role"] == "teacher"
        assert client.get("/auth/me", headers=bearer(token)).json()["role"] == "teacher"
        (event,) = store.audit_for(user_id)
        assert (event.kind, event.reason) == ("role_granted", "student->teacher:invitation")

    def test_it_forgives_case_spaces_and_hyphens(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, _ = _signed_in(client)
        _invite(store, code="ABCD-EFGH-JKMN")

        response = client.post(
            "/auth/teacher-invite", json={"code": " abcd efgh-jkmn "}, headers=bearer(token)
        )

        assert response.json()["role"] == "teacher"

    def test_it_works_once(self, client: TestClient, store: InMemoryStore) -> None:
        first, _ = _signed_in(client, "one@example.lk")
        second, second_id = _signed_in(client, "two@example.lk")
        code = _invite(store)
        client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(first))

        response = client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(second))

        assert response.status_code == 400
        assert store.get_user(second_id).role is Role.STUDENT

    def test_an_expired_one_does_nothing(self, client: TestClient, store: InMemoryStore) -> None:
        token, user_id = _signed_in(client)
        code = _invite(store, days=-1)

        response = client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(token))

        assert response.status_code == 400
        assert store.get_user(user_id).role is Role.STUDENT
        assert store.audit_for(user_id) == []

    def test_unknown_used_and_expired_are_one_answer(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, _ = _signed_in(client, "one@example.lk")
        other, _ = _signed_in(client, "two@example.lk")
        used = _invite(store)
        client.post("/auth/teacher-invite", json={"code": used}, headers=bearer(other))
        expired = _invite(store, days=-1)

        answers = {
            client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(token)).text
            for code in (used, expired, "NOPE-NOPE-NOPE")
        }

        assert len(answers) == 1

    def test_a_teacher_cannot_spend_one_meant_for_someone_else(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        token, user_id = _signed_in(client)
        store.set_role(user_id, Role.TEACHER)
        code = _invite(store)

        response = client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(token))

        assert response.status_code == 409
        # Still unspent, for the student it was meant for.
        _, student_id = _signed_in(client, "student@example.lk")
        assert store.redeem_invite(codes.code_hash(code), student_id, datetime.now(UTC).isoformat())

    def test_signed_out_it_does_nothing(self, client: TestClient, store: InMemoryStore) -> None:
        code = _invite(store)
        assert client.post("/auth/teacher-invite", json={"code": code}).status_code == 401


class TestARoleSurvivesAccountWrites:
    def test_changing_a_password_keeps_a_teacher_a_teacher(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        """The route writes the whole account back from a copy taken before."""
        token, user_id = _signed_in(client)
        store.set_role(user_id, Role.TEACHER)

        client.post(
            "/auth/password",
            json={"current_password": GOOD_PASSWORD, "new_password": "another-long-password"},
            headers=bearer(token),
        )

        assert store.get_user(user_id).role is Role.TEACHER

    def test_a_stale_whole_user_write_cannot_demote(self, store: InMemoryStore) -> None:
        from sinhala_reader.storage import User

        user = store.put_user(
            User(
                user_id="usr_1",
                email="a@example.lk",
                email_key="a@example.lk",
                password_hash="x",
                display_name="A",
            )
        )
        store.set_role(user.user_id, Role.TEACHER)

        store.put_user(replace(user, display_name="Renamed"))

        got = store.get_user(user.user_id)
        assert got is not None
        assert (got.display_name, got.role) == ("Renamed", Role.TEACHER)


class TestTheCommandLine:
    def test_grants_a_role_and_audits_it(self, client: TestClient, store: InMemoryStore) -> None:
        _, user_id = _signed_in(client, "Teacher@School.lk")
        said: list[str] = []

        status = admin.main(
            [
                "grant-role",
                "--email",
                "teacher@school.lk",
                "--role",
                "teacher",
                "--reason",
                "verified-teacher",
            ],
            store=store,
            out=said.append,
        )

        assert status == 0
        assert store.get_user(user_id).role is Role.TEACHER
        (event,) = store.audit_for(user_id)
        assert (event.actor, event.reason) == ("cli", "student->teacher:verified-teacher")
        assert said == ["Teacher@School.lk is now a teacher."]

    def test_an_unknown_address_changes_nothing(self, store: InMemoryStore) -> None:
        said: list[str] = []
        status = admin.main(
            [
                "grant-role",
                "--email",
                "nobody@example.lk",
                "--role",
                "admin",
                "--reason",
                "school-staff",
            ],
            store=store,
            out=said.append,
        )
        assert status == 1

    def test_a_reason_must_be_one_of_the_codes(self, store: InMemoryStore) -> None:
        """Free text in an audit log is where private details end up."""
        with pytest.raises(SystemExit):
            admin.main(
                [
                    "grant-role",
                    "--email",
                    "a@example.lk",
                    "--role",
                    "teacher",
                    "--reason",
                    "she asked nicely",
                ],
                store=store,
                out=lambda _: None,
            )

    def test_prints_an_invitation_that_works_once(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        said: list[str] = []
        assert admin.main(["invite-teacher", "--days", "3"], store=store, out=said.append) == 0
        code = said[0].removeprefix("Teacher invitation: ")
        token, _ = _signed_in(client)

        response = client.post("/auth/teacher-invite", json={"code": code}, headers=bearer(token))

        assert response.json()["role"] == "teacher"

    def test_an_invitation_cannot_live_long(self, store: InMemoryStore) -> None:
        said: list[str] = []
        assert admin.main(["invite-teacher", "--days", "90"], store=store, out=said.append) == 1

    def test_refuses_to_act_on_a_store_that_forgets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SINHALA_READER_DATABASE_URL", raising=False)
        said: list[str] = []

        status = admin.main(["invite-teacher"], out=said.append)

        assert status == 2
        assert "No database" in said[0]


class TestResetsAndTheLog:
    def test_issue_reset_prints_a_code_that_recovers_the_account(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        _, user_id = _signed_in(client)
        said: list[str] = []

        status = admin.main(
            ["issue-reset", "--email", "nimali@example.lk", "--reason", "lost-code"],
            store=store,
            out=said.append,
        )

        assert status == 0
        code = said[0].rsplit(": ", 1)[1]
        recovered = client.post(
            "/auth/recover",
            json={
                "email": "nimali@example.lk",
                "recovery_code": code,
                "new_password": "a-brand-new-password",
            },
        )
        assert recovered.status_code == 200
        kinds = [e.kind for e in store.audit_for(user_id)]
        assert kinds == ["recovery_code_issued", "password_recovered"]

    def test_list_audit_shows_what_changed_an_account(
        self, client: TestClient, store: InMemoryStore
    ) -> None:
        _signed_in(client)
        admin.main(
            [
                "grant-role",
                "--email",
                "nimali@example.lk",
                "--role",
                "teacher",
                "--reason",
                "school-staff",
            ],
            store=store,
            out=lambda _: None,
        )
        said: list[str] = []

        assert (
            admin.main(["list-audit", "--email", "nimali@example.lk"], store=store, out=said.append)
            == 0
        )

        (line,) = said
        assert "role_granted" in line and "student->teacher:school-staff" in line


class TestCodes:
    def test_have_no_look_alike_characters(self) -> None:
        for _ in range(200):
            code = codes.new_code()
            assert not set(code) & set("01OIL")

    def test_are_grouped_in_fours(self) -> None:
        assert [len(group) for group in codes.new_code().split("-")] == [4, 4, 4]
