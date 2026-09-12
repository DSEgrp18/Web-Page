"""Study questions: private, cited evidence or an explicit abstention."""

from __future__ import annotations

from conftest import OTHER_READER, Page, Text, as_reader, build_pdf, upload
from fastapi.testclient import TestClient


def ask(client: TestClient, document_id: str, question: str, owner: str | None = None):
    return client.post(
        f"/documents/{document_id}/questions",
        json={"question": question},
        headers=as_reader(client, owner) if owner else as_reader(client),
    )


def test_a_supported_question_returns_an_extract_and_reachable_citation(client: TestClient) -> None:
    uploaded = upload(
        client,
        build_pdf(
            [
                Page(
                    blocks=(
                        Text("1814 වර්ෂයේ දී දුම්රිය එන්ජිම නිපදවීය."),
                        Text("එය ප්‍රවාහනයේ වැදගත් වෙනසක් විය.", y=680),
                    )
                )
            ]
        ),
    )
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["document_id"]
    page = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    segment = page["segments"][0]

    response = ask(client, document_id, segment["display_text"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["abstained"] is False
    assert segment["display_text"] in body["answer"]
    assert body["citations"]
    citation = body["citations"][0]
    assert citation["page_index"] == 0
    assert segment["segment_id"] in citation["segment_ids"]
    assert citation["quote"] == body["answer"]


def test_an_unsupported_question_abstains_instead_of_guessing(
    client: TestClient, prepared_document
) -> None:
    response = ask(client, prepared_document["document_id"], "පරිගණක ජාල ආරක්ෂාව ගැන කියන්න")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": prepared_document["document_id"],
        "answer": None,
        "citations": [],
        "abstained": True,
    }


def test_another_reader_cannot_ask_about_someone_else_s_book(
    client: TestClient, prepared_document
) -> None:
    response = ask(client, prepared_document["document_id"], "ප්‍රශ්නය", OTHER_READER)

    # Deliberately indistinguishable from a document that does not exist.
    assert response.status_code == 404


def test_an_empty_question_is_rejected_before_retrieval(
    client: TestClient, prepared_document
) -> None:
    response = ask(client, prepared_document["document_id"], "")

    assert response.status_code == 422
