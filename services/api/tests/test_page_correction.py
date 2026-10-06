"""Correcting a page: digits stay digits, and saving nothing changes nothing."""

from __future__ import annotations

from conftest import Page, Text, as_reader, build_pdf, upload
from fastapi.testclient import TestClient


def _document(client: TestClient) -> str:
    uploaded = upload(client, build_pdf([Page(blocks=(Text("පොත් කියවීම වැදගත් වේ."),))]))
    assert uploaded.status_code == 202, uploaded.text
    return uploaded.json()["document_id"]


def correct(client: TestClient, document_id: str, text: str):
    return client.post(
        f"/documents/{document_id}/pages/0/correction",
        json={"text": text},
        headers=as_reader(client),
    )


def test_a_correction_shows_its_numbers_as_written(client: TestClient) -> None:
    document_id = _document(client)
    response = correct(client, document_id, "ලකුණු 2,5 ක් සහ 0 ක් ලැබුණි.")
    assert response.status_code == 200, response.text
    page = response.json()
    shown = " ".join(segment["display_text"] for segment in page["segments"])
    assert "2,5" in shown and "බින්දුව" not in shown
    assert "note:page_corrected" in page["notes"]
    assert not any("teacher" in note for note in page["notes"])


def test_saving_the_unchanged_text_is_refused(client: TestClient) -> None:
    document_id = _document(client)
    before = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    current = " ".join(segment["display_text"] for segment in before["segments"])

    response = correct(client, document_id, current)

    assert response.status_code == 422, response.text
    after = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    assert after["notes"] == before["notes"]
