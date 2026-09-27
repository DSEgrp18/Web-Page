"""Phase 5: pasted text, search inside a book, and reporting a problem."""

from __future__ import annotations

import pytest
from conftest import sinhala_page
from test_publishing import School, cheap_hashing, sessions_auth  # noqa: F401

SINHALA = "ශ්‍රී ලංකාවේ අගනුවර කෝට්ටේ වේ."


@pytest.fixture
def school() -> School:
    return School()


class TestPastedText:
    def test_becomes_a_book_in_sections_with_its_title(self, school: School) -> None:
        text = "\n".join([SINHALA * 30] * 8)

        made = school.client.post(
            "/documents/text", json={"title": "සටහන්", "text": text}, headers=school.teacher
        )

        assert made.status_code == 202, made.text
        doc = made.json()
        assert doc["title"] == "සටහන්" and doc["media_type"] == "text/plain"
        detail = school.client.get(f"/documents/{doc['document_id']}", headers=school.teacher)
        assert detail.json()["page_count"] > 1

    def test_over_the_limit_is_refused(self, school: School) -> None:
        refused = school.client.post(
            "/documents/text", json={"text": "අ" * 200_001}, headers=school.teacher
        )

        assert refused.status_code == 422

    def test_blank_is_refused(self, school: School) -> None:
        refused = school.client.post(
            "/documents/text", json={"text": "   \n  "}, headers=school.teacher
        )

        assert refused.status_code == 400


def search(school: School, doc: str, q: str, who):
    return school.client.get(f"/documents/{doc}/search", params={"q": q}, headers=who)


class TestSearch:
    def test_finds_the_books_own_sentences_in_order(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        page = school.client.get(f"/documents/{doc}/pages/0", headers=school.teacher).json()
        first = page["segments"][0]
        word = first["display_text"].split()[0]

        found = search(school, doc, word, school.teacher).json()

        assert found["exact"][0]["segment_id"] == first["segment_id"]
        assert all(word in hit["text"] for hit in found["exact"])
        assert found["related"] and found["related"][0]["segment_id"]

    def test_says_nothing_matched_rather_than_guessing(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

        found = search(school, doc, "zzzqqq", school.teacher).json()

        assert found["exact"] == [] and found["related"] == []

    def test_is_absent_for_a_book_they_cannot_read(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

        assert search(school, doc, "අ", school.student).status_code == 404


def report(school: School, who, **body):
    return school.client.post("/reports", json={"message": "වැරදියි", **body}, headers=who)


class TestReports:
    def test_a_student_reports_a_sentence_and_the_teacher_reads_it(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        page = school.client.get(f"/documents/{doc}/pages/0", headers=school.student).json()
        segment = page["segments"][0]

        sent = report(
            school,
            school.student,
            kind="pronunciation",
            document_id=doc,
            segment_id=segment["segment_id"],
        )
        seen = school.client.get(f"/documents/{doc}/reports", headers=school.teacher).json()

        assert sent.status_code == 201, sent.text
        [one] = seen
        assert one["kind"] == "pronunciation" and one["sentence"] == segment["display_text"]
        assert "reporter" not in one and school.student_id not in str(one)

    def test_only_the_owner_reads_them(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        refused = school.client.get(f"/documents/{doc}/reports", headers=school.student)

        assert refused.status_code == 404

    def test_cannot_be_made_on_a_book_they_cannot_read(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

        refused = report(school, school.student, kind="extraction", document_id=doc)

        assert refused.status_code == 404
        assert school.store.reports_on(doc, school.teacher_id) == []

    def test_about_the_site_needs_no_book(self, school: School) -> None:
        sent = report(school, school.student, kind="accessibility")

        assert sent.status_code == 201

    def test_go_with_the_book(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        report(school, school.teacher, kind="other", document_id=doc)

        school.client.delete(f"/documents/{doc}", headers=school.teacher)

        assert school.store.reports_on(doc, school.teacher_id) == []
