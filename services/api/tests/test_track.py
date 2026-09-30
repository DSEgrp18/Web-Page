"""Track: heard sentences, spaced review, the progress page, and what a teacher
may see of it (only students who chose to share)."""

from __future__ import annotations

from datetime import datetime

import pytest
from conftest import lesson_page
from test_publishing import School, cheap_hashing, sessions_auth  # noqa: F401

from sinhala_reader import track


class TestTheSchedule:
    def test_a_first_right_answer_comes_back_tomorrow(self) -> None:
        assert track.schedule(None, True, "2026-09-10") == (1, "2026-09-11")

    def test_a_right_answer_when_due_moves_up_a_box(self) -> None:
        assert track.schedule((2, "2026-09-10"), True, "2026-09-10") == (3, "2026-09-14")

    def test_the_top_box_stays_the_top_box(self) -> None:
        assert track.schedule((5, "2026-09-10"), True, "2026-09-10") == (5, "2026-09-26")

    def test_a_wrong_answer_goes_back_to_box_one(self) -> None:
        assert track.schedule((4, "2026-09-10"), False, "2026-09-10") == (1, "2026-09-11")

    def test_answering_again_before_it_is_due_changes_nothing(self) -> None:
        assert track.schedule((3, "2026-09-14"), True, "2026-09-10") == (3, "2026-09-14")

    def test_answers_from_before_scheduling_are_due(self) -> None:
        assert track.is_due("", "2026-09-10")

    def test_the_day_is_colombos(self) -> None:
        # 20:00 UTC is already the next morning in Colombo.
        assert track.today(datetime.fromisoformat("2026-09-10T20:00:00+00:00")) == "2026-09-11"


class TestChapterRows:
    def test_heard_and_answered_fall_in_their_chapters(self) -> None:
        bits = track.set_bits(b"", [0, 1, 2])
        rows = track.chapter_rows(
            [(0, 0), (1, 0), (2, 1), (3, 2)],
            [("One", 0), ("Two", 2)],
            bits,
            [track.Answered(2, True, False), track.Answered(1, False, True)],
        )

        assert [(r.title, r.sentences, r.heard, r.complete) for r in rows] == [
            ("One", 3, 3, True),
            ("Two", 1, 0, False),
        ]
        assert (rows[0].answered, rows[0].correct, rows[0].due) == (1, 0, 1)
        assert (rows[1].answered, rows[1].correct) == (1, 1)

    def test_a_book_without_chapters_is_one_row(self) -> None:
        rows = track.chapter_rows([(0, 0), (1, 3)], None, b"", [])

        assert [(r.title, r.sentences) for r in rows] == [(None, 2)]


@pytest.fixture
def school() -> School:
    return School()


def segments_of(school: School, doc: str, who) -> list[str]:
    page = school.client.get(f"/documents/{doc}/pages/0", headers=who).json()
    return [s["segment_id"] for s in page["segments"]]


class TestWhatAReaderHasHeard:
    def test_counts_toward_their_progress(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        ids = segments_of(school, doc, school.teacher)

        sent = school.client.post(
            f"/documents/{doc}/heard", json={"segment_ids": ids}, headers=school.teacher
        )
        report = school.client.get("/progress", headers=school.teacher).json()

        assert sent.status_code == 204
        [book] = report["books"]
        assert sum(c["heard"] for c in book["chapters"]) == len(ids)
        assert report["chapters_complete"] == report["chapter_count"] >= 1

    def test_is_theirs_alone(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        ids = segments_of(school, doc, school.teacher)
        school.client.post(
            f"/documents/{doc}/heard", json={"segment_ids": ids}, headers=school.teacher
        )

        report = school.client.get("/progress", headers=school.student).json()

        [book] = report["books"]
        assert sum(c["heard"] for c in book["chapters"]) == 0

    def test_cannot_be_reported_for_a_book_they_cannot_read(self, school: School) -> None:
        doc = school.upload([lesson_page()])

        refused = school.client.post(
            f"/documents/{doc}/heard", json={"segment_ids": ["x"]}, headers=school.student
        )

        assert refused.status_code == 404


def answer_wrong(school: School, doc: str, who) -> str:
    quiz = school.client.post(f"/documents/{doc}/quizzes", json={}, headers=who).json()
    question = quiz["questions"][0]
    wrong = ((question.get("answer") or 0) + 1) % len(question["options"])
    school.client.post(
        f"/quizzes/{quiz['quiz_id']}/answers",
        json={"question_id": question["question_id"], "choice": wrong},
        headers=who,
    )
    return quiz["quiz_id"]


class TestRevision:
    def test_a_wrong_answer_is_due_tomorrow_and_then_listed(
        self, school: School, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc = school.upload([lesson_page()])
        quiz_id = answer_wrong(school, doc, school.teacher)

        assert school.client.get("/progress", headers=school.teacher).json()["due"] == 0

        monkeypatch.setattr(track, "today", lambda now=None: "2999-01-01")
        report = school.client.get("/progress", headers=school.teacher).json()
        detail = school.client.get(f"/quizzes/{quiz_id}", headers=school.teacher).json()

        assert report["due"] == 1
        assert report["revise"] == [
            {"document_id": doc, "title": "book.pdf", "quiz_id": quiz_id, "due": 1}
        ]
        assert [a["due"] for a in detail["answers"]] == [True]


class TestTheTeachersView:
    def class_view(self, school: School):
        return school.client.get(f"/classes/{school.class_id}/progress", headers=school.teacher)

    def test_shows_nobody_who_has_not_chosen_to_share(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)

        view = self.class_view(school).json()

        assert view["students"] == [] and view["not_sharing"] == 1

    def test_shows_a_student_who_shares_on_class_books_only(self, school: School) -> None:
        shared = school.upload([lesson_page()])
        school.publish(shared)
        school.upload([lesson_page()])  # the teacher's own, not published
        own = school.upload([lesson_page()], who=school.student)
        answer_wrong(school, shared, school.student)  # a personal quiz: private
        for doc in (shared, own):
            ids = segments_of(school, doc, school.student)
            school.client.post(
                f"/documents/{doc}/heard", json={"segment_ids": ids}, headers=school.student
            )
        school.client.put(
            f"/classes/{school.class_id}/share-progress",
            json={"share": True},
            headers=school.student,
        )

        view = self.class_view(school).json()

        [student] = view["students"]
        assert view["not_sharing"] == 0 and student["display_name"] == "student"
        assert [b["document_id"] for b in student["books"]] == [shared]
        chapters = student["books"][0]["chapters"]
        assert sum(c["heard"] for c in chapters) > 0
        assert sum(c["answered"] for c in chapters) == 0

    def test_stops_the_moment_sharing_is_withdrawn(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        url = f"/classes/{school.class_id}/share-progress"
        school.client.put(url, json={"share": True}, headers=school.student)
        school.client.put(url, json={"share": False}, headers=school.student)

        assert self.class_view(school).json()["students"] == []

    def test_is_the_teachers_alone(self, school: School) -> None:
        refused = school.client.get(f"/classes/{school.class_id}/progress", headers=school.student)

        assert refused.status_code == 404

    def test_downloads_as_a_spreadsheet(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        school.client.put(
            f"/classes/{school.class_id}/share-progress",
            json={"share": True},
            headers=school.student,
        )

        sheet = school.client.get(
            f"/classes/{school.class_id}/progress.csv", headers=school.teacher
        )

        assert sheet.headers["content-type"].startswith("text/csv")
        lines = sheet.content.decode("utf-8-sig").splitlines()
        assert lines[0].startswith("student,book,chapter") and lines[1].startswith("student,")


def test_deleting_the_book_deletes_what_was_heard(school: School) -> None:
    doc = school.upload([lesson_page()])
    ids = segments_of(school, doc, school.teacher)
    school.client.post(f"/documents/{doc}/heard", json={"segment_ids": ids}, headers=school.teacher)

    school.client.delete(f"/documents/{doc}", headers=school.teacher)

    assert school.store.get_heard(doc, school.teacher_id) is None
