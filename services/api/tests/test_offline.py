"""The offline manifest: one chapter, saying which sentences have audio."""

from __future__ import annotations

import pytest
from conftest import sinhala_page
from test_publishing import School, cheap_hashing, sessions_auth  # noqa: F401


@pytest.fixture
def school() -> School:
    return School()


def manifest(school: School, doc: str, who, page: int = 0):
    return school.client.get(f"/documents/{doc}/offline", params={"page": page}, headers=who)


def test_lists_the_sentences_and_which_have_audio(school: School) -> None:
    doc = school.upload([sinhala_page()])
    page = school.client.get(f"/documents/{doc}/pages/0", headers=school.teacher).json()
    first = page["segments"][0]["segment_id"]
    school.client.get(f"/documents/{doc}/segments/{first}/audio", headers=school.teacher)

    found = manifest(school, doc, school.teacher).json()

    assert found["total"] == len(page["segments"]) and found["ready"] == 1
    assert [c["segment_id"] for c in found["clips"] if c["ready"]] == [first]
    assert found["title"] == "book.pdf" and found["truncated"] is False


def test_a_class_reader_sees_the_teachers_audio_as_ready(school: School) -> None:
    doc = school.upload([sinhala_page()])
    school.publish(doc)
    page = school.client.get(f"/documents/{doc}/pages/0", headers=school.student).json()
    first = page["segments"][0]["segment_id"]
    school.client.get(f"/documents/{doc}/segments/{first}/audio", headers=school.student)

    found = manifest(school, doc, school.student).json()

    assert found["ready"] == 1


def test_is_absent_for_a_book_they_cannot_read(school: School) -> None:
    doc = school.upload([sinhala_page()])

    assert manifest(school, doc, school.student).status_code == 404
