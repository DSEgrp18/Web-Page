"""A reader chooses the voice, and a voice that is not installed is refused.

XTTS conditions on a reference clip, so a second voice is a second clip beside
the checkpoint. Until a clip is installed its voice does not exist, and asking
for it must fail plainly: CLAUDE.md forbids answering in another voice instead.
"""

from __future__ import annotations

import pytest
from conftest import as_reader, upload
from fastapi.testclient import TestClient
from sinhala_tts.adapter import DEFAULT_VOICE, DevelopmentAdapter

from sinhala_reader import Deps, create_app
from sinhala_reader.storage import InMemoryStore


class FemaleOnly(DevelopmentAdapter):
    """The placeholder voice, with only the default clip installed."""

    def voices(self) -> dict[str, str]:
        return {DEFAULT_VOICE: f"development-{DEFAULT_VOICE}"}


def client_with(adapter: DevelopmentAdapter) -> TestClient:
    return TestClient(
        create_app(Deps(store=InMemoryStore(), adapter=adapter, run_in_background=False))
    )


def first_segment(client: TestClient, book: bytes) -> str:
    document_id = upload(client, book).json()["document_id"]
    page = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    return f"/documents/{document_id}/segments/{page['segments'][0]['segment_id']}/audio"


def test_each_voice_is_its_own_audio(book: bytes) -> None:
    client = client_with(DevelopmentAdapter())
    audio = first_segment(client, book)

    for voice in ("si-female", "si-male"):
        response = client.get(audio, params={"voice": voice}, headers=as_reader(client))
        assert response.status_code == 200, response.text
        manifest = client.get(
            f"{audio}/manifest", params={"voice": voice}, headers=as_reader(client)
        ).json()
        assert manifest["generated"] is True
        assert manifest["voice_id"] == f"development-{voice}"


def test_no_voice_named_means_the_default(book: bytes) -> None:
    client = client_with(DevelopmentAdapter())
    audio = first_segment(client, book)
    assert client.get(audio, headers=as_reader(client)).status_code == 200
    manifest = client.get(f"{audio}/manifest", headers=as_reader(client)).json()
    assert manifest["voice_id"] == "development-si-female"


@pytest.mark.parametrize("voice", ["si-male", "en-robot"])
def test_a_voice_that_is_not_installed_is_refused_not_substituted(book: bytes, voice: str) -> None:
    client = client_with(FemaleOnly())
    audio = first_segment(client, book)

    response = client.get(audio, params={"voice": voice}, headers=as_reader(client))

    assert response.status_code == 409
    assert response.json()["detail"] == "This voice is not available yet."


def test_readiness_lists_the_voices_a_reader_can_choose() -> None:
    assert client_with(FemaleOnly()).get("/readiness").json()["voices"] == ["si-female"]
    assert client_with(DevelopmentAdapter()).get("/readiness").json()["voices"] == [
        "si-female",
        "si-male",
    ]
