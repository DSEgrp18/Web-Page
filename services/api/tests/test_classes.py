"""Classes: a teacher's students, joined by code and let in by the teacher.

What matters most here is who can see what. A student sees the class name and
their teacher's name, never the code or the other students. A teacher sees
their members' display names and standing, never an email address. Anyone
else sees nothing at all: a class they are not part of is absent, not
forbidden.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_accounts import register

from sinhala_reader import Deps, create_app, passwords, ratelimit
from sinhala_reader.ratelimit import LIMITS, Limit
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore, MemberState, Role


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


class Person:
    """A signed-in account, and the headers to act as it."""

    def __init__(self, client: TestClient, email: str, name: str) -> None:
        body = register(client, email=email, name=name).json()
        self.user_id: str = body["account"]["user_id"]
        self.headers = {"Authorization": f"Bearer {body['token']}"}


@pytest.fixture
def teacher(client: TestClient, store: InMemoryStore) -> Person:
    person = Person(client, "teacher@school.lk", "ගුරු")
    store.set_role(person.user_id, Role.TEACHER)
    return person


@pytest.fixture
def student(client: TestClient) -> Person:
    return Person(client, "student@school.lk", "සිසු")


def make_class(client: TestClient, teacher: Person, name: str = "10 ශ්‍රේණිය") -> dict:
    response = client.post("/classes", json={"name": name}, headers=teacher.headers)
    assert response.status_code == 201, response.text
    return response.json()


def join(client: TestClient, person: Person, code: str):
    return client.post("/classes/join", json={"code": code}, headers=person.headers)


class TestMakingAClass:
    def test_a_teacher_makes_one_with_an_eight_digit_code(
        self, client: TestClient, teacher: Person
    ) -> None:
        made = make_class(client, teacher)

        assert made["name"] == "10 ශ්‍රේණිය"
        assert len(made["join_code"]) == 8 and made["join_code"].isdigit()
        assert made["members"] == []

    def test_a_student_cannot(self, client: TestClient, student: Person) -> None:
        response = client.post("/classes", json={"name": "x"}, headers=student.headers)
        assert response.status_code == 403

    def test_a_blank_name_is_refused(self, client: TestClient, teacher: Person) -> None:
        response = client.post("/classes", json={"name": "   "}, headers=teacher.headers)
        assert response.status_code == 422

    def test_signed_out_nothing_happens(self, client: TestClient) -> None:
        assert client.post("/classes", json={"name": "x"}).status_code == 401


class TestJoining:
    def test_joining_waits_for_the_teacher(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)

        joined = join(client, student, made["join_code"]).json()

        assert joined["state"] == "pending"
        assert joined["teacher_name"] == "ගුරු"
        # The code is the teacher's to share, not something a member is shown.
        assert "join_code" not in joined

    def test_spaces_and_hyphens_in_the_code_are_forgiven(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        code = make_class(client, teacher)["join_code"]

        assert join(client, student, f"{code[:4]} {code[4:]}").status_code == 200

    def test_a_wrong_code_says_only_that(self, client: TestClient, student: Person) -> None:
        response = join(client, student, "00000000")
        assert response.status_code == 404
        assert response.json()["detail"] == "No class has that code."

    def test_a_teacher_does_not_join_their_own_class(
        self, client: TestClient, teacher: Person
    ) -> None:
        code = make_class(client, teacher)["join_code"]
        assert join(client, teacher, code).status_code == 404

    def test_joining_twice_changes_nothing(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        client.post(
            f"/classes/{made['class_id']}/members/{student.user_id}/approve",
            headers=teacher.headers,
        )

        again = join(client, student, made["join_code"]).json()

        assert again["state"] == "active"

    def test_guessing_codes_is_rate_limited(
        self, client: TestClient, student: Person, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratelimit, "LIMITS", {**LIMITS, "join": Limit(2, 3600)})
        codes = [join(client, student, f"1234567{i}").status_code for i in range(3)]
        assert codes == [404, 404, 429]


class TestTheTeacher:
    def test_sees_members_by_name_and_standing_only(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])

        detail = client.get(f"/classes/{made['class_id']}", headers=teacher.headers).json()

        (member,) = detail["members"]
        assert member == {
            "user_id": student.user_id,
            "display_name": "සිසු",
            "state": "pending",
            "share_progress": False,
            "joined_at": member["joined_at"],
        }
        assert "student@school.lk" not in str(detail)

    def test_approves_and_removes_and_both_are_recorded(
        self, client: TestClient, teacher: Person, student: Person, store: InMemoryStore
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        base = f"/classes/{made['class_id']}/members/{student.user_id}"

        approved = client.post(f"{base}/approve", headers=teacher.headers).json()
        assert approved["members"][0]["state"] == "active"
        removed = client.post(f"{base}/remove", headers=teacher.headers).json()
        assert removed["members"][0]["state"] == "removed"

        kinds = [e.kind for e in store.audit_for(student.user_id)]
        assert kinds == ["member_active", "member_removed"]

    def test_a_removed_student_no_longer_sees_the_class(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        client.post(
            f"/classes/{made['class_id']}/members/{student.user_id}/remove",
            headers=teacher.headers,
        )

        assert (
            client.get(f"/classes/{made['class_id']}", headers=student.headers).status_code == 404
        )
        assert client.get("/classes", headers=student.headers).json()["joined"] == []

    def test_a_removed_student_asking_again_waits_again(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        client.post(
            f"/classes/{made['class_id']}/members/{student.user_id}/remove",
            headers=teacher.headers,
        )

        assert join(client, student, made["join_code"]).json()["state"] == "pending"

    def test_a_new_code_stops_the_old_one(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)

        renewed = client.post(f"/classes/{made['class_id']}/code", headers=teacher.headers).json()

        assert renewed["join_code"] != made["join_code"]
        assert join(client, student, made["join_code"]).status_code == 404
        assert join(client, student, renewed["join_code"]).status_code == 200

    def test_renames_and_deletes(self, client: TestClient, teacher: Person) -> None:
        made = make_class(client, teacher)
        url = f"/classes/{made['class_id']}"

        renamed = client.patch(url, json={"name": "11 ශ්‍රේණිය"}, headers=teacher.headers)
        assert renamed.json()["name"] == "11 ශ්‍රේණිය"
        assert client.delete(url, headers=teacher.headers).status_code == 204
        assert client.get(url, headers=teacher.headers).status_code == 404


class TestSomeoneElse:
    """Another teacher, a member, a stranger: absent, never forbidden."""

    def test_another_teacher_cannot_see_or_change_a_class(
        self, client: TestClient, teacher: Person, student: Person, store: InMemoryStore
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        other = Person(client, "other@school.lk", "වෙනත්")
        store.set_role(other.user_id, Role.TEACHER)
        url = f"/classes/{made['class_id']}"

        answers = [
            client.get(url, headers=other.headers).status_code,
            client.patch(url, json={"name": "x"}, headers=other.headers).status_code,
            client.post(f"{url}/code", headers=other.headers).status_code,
            client.post(
                f"{url}/members/{student.user_id}/approve", headers=other.headers
            ).status_code,
            client.delete(url, headers=other.headers).status_code,
        ]

        assert answers == [404] * 5
        assert store.membership(made["class_id"], student.user_id).state is MemberState.PENDING

    def test_a_member_cannot_act_as_the_teacher(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])
        url = f"/classes/{made['class_id']}"

        assert (
            client.post(
                f"{url}/members/{student.user_id}/approve", headers=student.headers
            ).status_code
            == 404
        )
        assert client.post(f"{url}/code", headers=student.headers).status_code == 404

    def test_a_stranger_sees_nothing(self, client: TestClient, teacher: Person) -> None:
        made = make_class(client, teacher)
        stranger = Person(client, "stranger@example.lk", "?")

        assert (
            client.get(f"/classes/{made['class_id']}", headers=stranger.headers).status_code == 404
        )
        assert client.get("/classes", headers=stranger.headers).json() == {
            "teaching": [],
            "joined": [],
        }


class TestTheStudentsChoices:
    def test_sharing_progress_is_off_until_they_turn_it_on(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        assert join(client, student, made["join_code"]).json()["share_progress"] is False
        url = f"/classes/{made['class_id']}/share-progress"

        on = client.put(url, json={"share": True}, headers=student.headers).json()
        assert on["share_progress"] is True
        seen = client.get(f"/classes/{made['class_id']}", headers=teacher.headers).json()
        assert seen["members"][0]["share_progress"] is True

        off = client.put(url, json={"share": False}, headers=student.headers).json()
        assert off["share_progress"] is False

    def test_only_they_can_make_that_choice(
        self, client: TestClient, teacher: Person, student: Person
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])

        response = client.put(
            f"/classes/{made['class_id']}/share-progress",
            json={"share": True},
            headers=teacher.headers,
        )

        assert response.status_code == 404

    def test_leaving_takes_everything_of_theirs(
        self, client: TestClient, teacher: Person, student: Person, store: InMemoryStore
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])

        response = client.delete(f"/classes/{made['class_id']}/membership", headers=student.headers)

        assert response.status_code == 204
        assert store.membership(made["class_id"], student.user_id) is None
        teacher_view = client.get(f"/classes/{made['class_id']}", headers=teacher.headers).json()
        assert teacher_view["members"] == []

    def test_deleting_their_account_takes_their_memberships(
        self, client: TestClient, teacher: Person, student: Person, store: InMemoryStore
    ) -> None:
        made = make_class(client, teacher)
        join(client, student, made["join_code"])

        client.request(
            "DELETE",
            "/auth/account",
            json={"current_password": "a-long-enough-password"},
            headers=student.headers,
        )

        assert store.members(made["class_id"], teacher.user_id) == []
