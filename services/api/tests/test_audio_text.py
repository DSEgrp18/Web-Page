"""The voice is given the text the pipeline prepared, not the text on screen.

The pipeline writes a segment's spoken text knowing what the segment is. "1.1"
inside a heading is a section number, read as an identifier; the same digits
in a sentence are a decimal. That decision is made once, with the role in
hand, and stored with the segment as ``spoken_text`` and ``model_text``.

If the voice is handed ``display_text`` instead, the adapter normalises it
again without knowing the role, and the heading is read as one point one. A
reader sees a section number and hears a decimal, with no way to tell that is
what happened. ``docs/accessible-ui-guide.md`` already says it plainly: never
speak ``display_text`` directly.

These tests rewrite a segment's stored text to something the adapter would
never derive from the screen, and check that is what reaches the voice.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import as_reader, upload
from fastapi.testclient import TestClient
from sinhala_documents.serialise import from_json, to_json
from sinhala_tts.adapter import DevelopmentAdapter
from sinhala_tts.normalize import to_model_input

from sinhala_reader import Deps, create_app
from sinhala_reader.preparation import forget_prepared
from sinhala_reader.storage import InMemoryStore

#: What the pipeline writes for a heading reading "1.1": section one one. Chosen
#: because the adapter could never produce it from the page's display text.
STORED_SPOKEN = "එක එක"
STORED_MODEL = "eka eka"


class RecordingAdapter(DevelopmentAdapter):
    """The placeholder voice, noting the model input it was actually given."""

    def __init__(self) -> None:
        super().__init__()
        self.given: list[str] = []

    def synthesize(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        result = super().synthesize(*args, **kwargs)
        self.given.append(result.metadata.model_text)
        return result


@pytest.fixture
def voice() -> RecordingAdapter:
    return RecordingAdapter()


@pytest.fixture
def deps(voice: RecordingAdapter) -> Deps:
    return Deps(store=InMemoryStore(), adapter=voice, run_in_background=False)


@pytest.fixture
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


@pytest.fixture
def heading(client: TestClient, deps: Deps, book: bytes) -> tuple[str, str, str]:
    """A prepared book whose first segment carries a heading's stored text.

    Returns the document id, the segment id, and that segment's display text.
    """
    document_id = upload(client, book).json()["document_id"]
    prepared = from_json(deps.store.get_prepared(document_id))
    first = prepared.segments[0]
    assert to_model_input(first.display_text) != STORED_MODEL, "precondition"

    pages = tuple(
        replace(
            page,
            segments=tuple(
                replace(s, spoken_text=STORED_SPOKEN, model_text=STORED_MODEL)
                if s.segment_id == first.segment_id
                else s
                for s in page.segments
            ),
        )
        for page in prepared.pages
    )
    deps.store.put_prepared(document_id, to_json(replace(prepared, pages=pages)))
    forget_prepared(document_id)
    return document_id, first.segment_id, first.display_text


def test_a_segment_is_voiced_from_its_stored_spoken_text(
    client: TestClient, voice: RecordingAdapter, heading: tuple[str, str, str]
) -> None:
    document_id, segment_id, _ = heading

    response = client.get(
        f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(client)
    )

    assert response.status_code == 200, response.text
    assert voice.given == [STORED_MODEL]


def test_the_manifest_finds_the_audio_the_route_made(
    client: TestClient, heading: tuple[str, str, str]
) -> None:
    """Both routes must derive the key from the same text.

    If only the audio route moved to the stored text, the manifest would look
    for a key nothing was ever saved under and report the audio as missing.
    """
    document_id, segment_id, _ = heading
    base = f"/documents/{document_id}/segments/{segment_id}/audio"

    assert client.get(base, headers=as_reader(client)).status_code == 200
    manifest = client.get(f"{base}/manifest", headers=as_reader(client)).json()

    assert manifest["generated"] is True
