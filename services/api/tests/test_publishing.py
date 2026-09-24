"""Publishing: a teacher reviews a book, attests the right to share it, and
shares it with a class, which then reads the version that was shared.

The access matrix checks who can reach what. These check the steps: the
review that must come first, withheld pages staying out of everything a class
reads, the pin, the audio made once for the class, and that stopping sharing,
removing a student and deleting a book all take effect at once.
"""

from __future__ import annotations

import pytest
from conftest import build_pdf, legacy_page, sinhala_page
from fastapi.testclient import TestClient
from sinhala_documents.ocr import OcrMode
from test_accounts import register
from test_ocr import CountingOcr

from sinhala_reader import Deps, create_app, passwords
from sinhala_reader.preparation import PreparationService, inline
from sinhala_reader.routes.common import WITHHELD_NOTE
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore, Role


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "SCRYPT_LOG_N", 8)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    import sinhala_reader.accounts as accounts

    monkeypatch.setattr(accounts, "_ABSENT_ACCOUNT_HASH", None)


@pytest.fixture(autouse=True)
def sessions_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_MODE_ENV, "sessions")


class School:
    """A teacher, their class with one approved student, and the client."""

    def __init__(self) -> None:
        self.store = InMemoryStore()
        deps = Deps(store=self.store, run_in_background=False, warm_on_start=False)
        # Pages whose text layer failed are read by a fake OCR, which flags them
        # for review, the way a real scanned page is flagged.
        deps.preparation = PreparationService(
            self.store, dispatch=inline, ocr=CountingOcr(), ocr_mode=OcrMode.BROKEN
        )
        self.client = TestClient(create_app(deps), headers={"X-Session-Transport": "bearer"})
        self.teacher, self.teacher_id = self._person("teacher@school.lk", Role.TEACHER)
        self.student, self.student_id = self._person("student@school.lk")
        room = self.client.post("/classes", json={"name": "A"}, headers=self.teacher).json()
        self.class_id = room["class_id"]
        self.client.post("/classes/join", json={"code": room["join_code"]}, headers=self.student)
        self.client.post(
            f"/classes/{self.class_id}/members/{self.student_id}/approve", headers=self.teacher
        )

    def _person(self, email: str, role: Role | None = None) -> tuple[dict[str, str], str]:
        body = register(self.client, email=email, name=email.split("@")[0]).json()
        if role is not None:
            self.store.set_role(body["account"]["user_id"], role)
        return {"Authorization": f"Bearer {body['token']}"}, body["account"]["user_id"]

    def upload(self, pages, who: dict[str, str] | None = None) -> str:
        response = self.client.post(
            "/documents",
            files={"file": ("book.pdf", build_pdf(pages), "application/pdf")},
            headers=who or self.teacher,
        )
        return response.json()["document_id"]

    def publish(self, doc: str, **overrides):
        body = {"class_ids": [self.class_id], "basis": "government_textbook", **overrides}
        return self.client.post(f"/documents/{doc}/publish", json=body, headers=self.teacher)


@pytest.fixture
def school() -> School:
    return School()


class TestReviewComesFirst:
    def test_a_scanned_page_must_be_decided_before_sharing(self, school: School) -> None:
        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])

        review = school.client.get(f"/documents/{doc}/review", headers=school.teacher).json()
        refused = school.publish(doc)

        assert [p["page_index"] for p in review["pages"]] == [1]
        assert review["undecided"] == 1 and review["ready_to_publish"] is False
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "unreviewed_pages"

    def test_once_decided_it_can_be_shared(self, school: School) -> None:
        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])

        decided = school.client.put(
            f"/documents/{doc}/review/1", json={"decision": "accepted"}, headers=school.teacher
        ).json()

        assert decided["ready_to_publish"] is True
        assert school.publish(doc).status_code == 200

    def test_a_page_that_needs_no_review_cannot_be_decided(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        response = school.client.put(
            f"/documents/{doc}/review/0", json={"decision": "withheld"}, headers=school.teacher
        )
        assert response.status_code == 404

    def test_a_book_with_nothing_flagged_is_ready(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        assert school.publish(doc).status_code == 200


class TestAWithheldPage:
    def test_is_not_read_to_the_class(self, school: School) -> None:
        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])
        school.client.put(
            f"/documents/{doc}/review/1", json={"decision": "withheld"}, headers=school.teacher
        )
        school.publish(doc)

        as_class = school.client.get(f"/documents/{doc}/pages/1", headers=school.student).json()
        as_owner = school.client.get(f"/documents/{doc}/pages/1", headers=school.teacher).json()

        assert as_class["segments"] == []
        assert as_class["notes"] == [WITHHELD_NOTE]
        # The teacher still sees their own book whole.
        assert as_owner["segments"]

    def test_is_not_an_answer_to_the_class(self, school: School) -> None:
        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])
        school.client.put(
            f"/documents/{doc}/review/1", json={"decision": "withheld"}, headers=school.teacher
        )
        school.publish(doc)

        # The fake OCR reads the withheld page as "පිළිගත් පාඨය".
        answer = school.client.post(
            f"/documents/{doc}/questions", json={"question": "පිළිගත් පාඨය"}, headers=school.student
        ).json()

        owners = school.client.post(
            f"/documents/{doc}/questions", json={"question": "පිළිගත් පාඨය"}, headers=school.teacher
        ).json()

        # The same question finds the page for its owner, so the class's
        # answer leaving it out is the withholding, not a miss.
        assert any(c["page_index"] == 1 for c in owners["citations"])
        assert all(c["page_index"] != 1 for c in answer["citations"])


class TestSharing:
    def test_only_a_teacher_can_share(self, school: School) -> None:
        doc = school.upload([sinhala_page()], who=school.student)
        response = school.client.post(
            f"/documents/{doc}/publish",
            json={"class_ids": [school.class_id], "basis": "own_work"},
            headers=school.student,
        )
        assert response.status_code == 403

    def test_not_with_someone_elses_class(self, school: School) -> None:
        other, _ = school._person("other@school.lk", Role.TEACHER)
        theirs = school.client.post("/classes", json={"name": "B"}, headers=other).json()
        doc = school.upload([sinhala_page()])

        response = school.publish(doc, class_ids=[theirs["class_id"]])

        assert response.status_code == 404
        assert (
            school.client.get(f"/documents/{doc}/publication", headers=school.teacher).json()
            is None
        )

    def test_other_needs_the_basis_spelled_out(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        assert school.publish(doc, basis="other").status_code == 422
        assert school.publish(doc, basis="other", note="ගුරු මාර්ගෝපදේශය").status_code == 200

    def test_the_attestation_is_recorded(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        publication = school.client.get(
            f"/documents/{doc}/publication", headers=school.teacher
        ).json()

        assert publication["basis"] == "government_textbook"
        assert publication["class_ids"] == [school.class_id]
        assert publication["stale"] is False
        kinds = [e.kind for e in school.store.audit_for(school.teacher_id)]
        assert "book_published" in kinds

    def test_the_class_finds_it_in_its_books(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        books = school.client.get("/class-books", headers=school.student).json()

        assert [(b["class_name"], b["book"]["document_id"]) for b in books] == [("A", doc)]
        # A teacher's own books are in their own library, not repeated here.
        assert school.client.get("/class-books", headers=school.teacher).json() == []


class TestTheClassHearsOneRecording:
    def test_a_students_audio_is_the_books_not_their_own_copy(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        seg = school.client.get(f"/documents/{doc}/pages/0", headers=school.student).json()[
            "segments"
        ][0]["segment_id"]

        school.client.get(f"/documents/{doc}/segments/{seg}/audio", headers=school.student)
        manifest = school.client.get(
            f"/documents/{doc}/segments/{seg}/audio/manifest", headers=school.teacher
        ).json()

        # Made once, when the student asked; the teacher's manifest finds it.
        assert manifest["generated"] is True


class TestEverythingTakesEffectAtOnce:
    def test_stopping_sharing_ends_the_class_access(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        assert school.client.get(f"/documents/{doc}", headers=school.student).status_code == 200

        stopped = school.client.delete(
            f"/documents/{doc}/classes/{school.class_id}", headers=school.teacher
        )

        assert stopped.status_code == 204
        assert school.client.get(f"/documents/{doc}", headers=school.student).status_code == 404

    def test_removing_a_student_ends_their_access(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        school.client.post(
            f"/classes/{school.class_id}/members/{school.student_id}/remove",
            headers=school.teacher,
        )

        assert school.client.get(f"/documents/{doc}", headers=school.student).status_code == 404

    def test_a_shared_book_is_not_deleted_until_it_is_unshared(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        refused = school.client.delete(f"/documents/{doc}", headers=school.teacher)
        school.client.delete(f"/documents/{doc}/classes/{school.class_id}", headers=school.teacher)
        deleted = school.client.delete(f"/documents/{doc}", headers=school.teacher)

        assert refused.status_code == 409
        assert deleted.status_code == 204
        assert school.client.get("/class-books", headers=school.student).json() == []


class TestWhatATeacherNeverSees:
    def test_a_students_bookmarks_on_a_class_book_stay_theirs(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        seg = school.client.get(f"/documents/{doc}/pages/0", headers=school.student).json()[
            "segments"
        ][0]["segment_id"]
        school.client.post(
            f"/documents/{doc}/bookmarks",
            json={"segment_id": seg, "note": "මගේ සටහන"},
            headers=school.student,
        )

        theirs = school.client.get(f"/documents/{doc}/bookmarks", headers=school.student).json()
        teachers = school.client.get(f"/documents/{doc}/bookmarks", headers=school.teacher).json()

        assert [b["note"] for b in theirs] == ["මගේ සටහන"]
        assert teachers == []


class TestVoicingAheadOfTime:
    """A shared book, voiced once for the class before anyone presses play."""

    def test_voices_every_sentence_the_class_will_hear(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        started = school.client.post(f"/documents/{doc}/prerender", headers=school.teacher)

        assert started.status_code == 202, started.text
        body = started.json()
        assert body["total"] > 0
        assert body["ready"] == body["total"]
        again = school.client.get(f"/documents/{doc}/prerender", headers=school.teacher).json()
        assert again == body

    def test_the_class_then_plays_without_voicing_anything(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        school.client.post(f"/documents/{doc}/prerender", headers=school.teacher)
        voiced = school.store.audio_keys(doc, school.teacher_id)
        page = school.client.get(f"/documents/{doc}/pages/0", headers=school.student).json()

        for segment in page["segments"]:
            played = school.client.get(
                f"/documents/{doc}/segments/{segment['segment_id']}/audio",
                headers=school.student,
            )
            assert played.status_code == 200

        assert school.store.audio_keys(doc, school.teacher_id) == voiced

    def test_skips_a_withheld_page(self, school: School) -> None:
        whole = school.upload([sinhala_page()])
        school.publish(whole)
        one_page = school.client.post(
            f"/documents/{whole}/prerender", headers=school.teacher
        ).json()["total"]

        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])
        school.client.put(
            f"/documents/{doc}/review/1", json={"decision": "withheld"}, headers=school.teacher
        )
        school.publish(doc)

        status_ = school.client.post(f"/documents/{doc}/prerender", headers=school.teacher).json()

        assert status_["total"] == one_page

    def test_only_a_shared_book(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

        refused = school.client.post(f"/documents/{doc}/prerender", headers=school.teacher)

        assert refused.status_code == 409
        assert school.store.audio_keys(doc, school.teacher_id) == set()

    def test_only_by_its_owner(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        as_student = school.client.post(f"/documents/{doc}/prerender", headers=school.student)
        status_as_student = school.client.get(f"/documents/{doc}/prerender", headers=school.student)

        assert (as_student.status_code, status_as_student.status_code) == (404, 404)
