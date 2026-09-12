"""The reader API, end to end.

The order here follows what a reader does: sign in, upload a book, wait for it,
read a page, hear a sentence, stop, come back. Interleaved with that are the
things CLAUDE.md names as release blockers — ownership, deletion, and never
presenting placeholder audio as narration — because those are the ones that fail
silently.
"""

from __future__ import annotations

import io
import wave

from conftest import OTHER_READER, READER, as_reader, build_pdf, legacy_page, sinhala_page, upload
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app
from sinhala_reader.app import REAL_MODEL_HEADER
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import Document, InMemoryStore, Job, new_id

# --------------------------------------------------------------------------
# Getting in
# --------------------------------------------------------------------------


def test_the_api_refuses_to_serve_without_configured_authentication(
    monkeypatch, client: TestClient
) -> None:
    """A deployment that forgets to configure auth must fail closed.

    Serving private books to whoever asks is the one failure that cannot be
    walked back, so the absence of a scheme is an error rather than a default.
    """
    monkeypatch.delenv(AUTH_MODE_ENV, raising=False)
    response = client.get("/documents", headers=as_reader(client))
    assert response.status_code == 503
    assert "authentication" in response.json()["detail"]


def test_a_request_with_no_identity_is_refused(client: TestClient) -> None:
    assert client.get("/documents").status_code == 401


def test_liveness_and_readiness_are_separate(client: TestClient) -> None:
    """The process being alive says nothing about a model being loaded."""
    assert client.get("/health").json() == {"alive": True}
    readiness = client.get("/readiness").json()
    assert readiness["alive"] is True
    assert "readiness" in readiness


def test_readiness_declares_every_way_this_is_not_production(client: TestClient) -> None:
    """Silence would imply these are handled. None of them are."""
    limitations = " ".join(client.get("/readiness").json()["limitations"])
    assert "placeholder tone" in limitations
    assert "in memory" in limitations
    assert "trusted header" in limitations


# --------------------------------------------------------------------------
# Uploading
# --------------------------------------------------------------------------


def test_uploading_returns_immediately_with_a_job(client: TestClient, book: bytes) -> None:
    """Preparing a book takes tens of seconds. The connection must not wait."""
    response = upload(client, book)
    assert response.status_code == 202
    body = response.json()
    assert body["document_id"]
    assert body["job"]["kind"] == "prepare"


def test_a_prepared_document_reports_its_pages_and_segments(prepared_document) -> None:
    assert prepared_document["job"]["state"] == "succeeded"
    assert prepared_document["page_count"] == 2
    assert prepared_document["segment_count"] > 0
    assert prepared_document["version"]


def test_a_file_that_is_not_a_pdf_is_refused_with_a_reason(client: TestClient) -> None:
    response = upload(client, b"this is not a pdf" + b"\x00" * 2000)
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_a_document_that_cannot_be_read_fails_its_job_without_leaking_text(
    client: TestClient,
) -> None:
    """A truncated PDF passes the header check and then fails to parse.

    The failure reaches the reader as a stage and a reason, never as a passage
    of their document.
    """
    broken = build_pdf([sinhala_page()])[:400]
    response = upload(client, broken)
    body = response.json()
    assert body["job"]["state"] == "failed"
    assert body["job"]["stage"] == "extracting"
    assert "පොත්" not in (body["job"]["detail"] or "")


# --------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------


def test_another_readers_document_is_absent_rather_than_forbidden(
    client: TestClient, prepared_document
) -> None:
    """404, not 403.

    A 403 on an id that exists confirms it exists. These are private books
    belonging to identifiable students.
    """
    document_id = prepared_document["document_id"]
    response = client.get(f"/documents/{document_id}", headers=as_reader(client, OTHER_READER))
    assert response.status_code == 404


def test_listing_only_shows_your_own_documents(client: TestClient, book: bytes) -> None:
    upload(client, book, READER)
    upload(client, book, OTHER_READER)
    mine = client.get("/documents", headers=as_reader(client, READER)).json()
    assert len(mine) == 1


def test_another_reader_cannot_reach_pages_segments_audio_or_progress(
    client: TestClient, prepared_document
) -> None:
    """Every route, not just the ones that look sensitive."""
    document_id = prepared_document["document_id"]
    intruder = as_reader(client, OTHER_READER)
    segment_id = _first_segment(client, document_id)["segment_id"]

    for path in (
        f"/documents/{document_id}",
        f"/documents/{document_id}/pages/0",
        f"/documents/{document_id}/segments/{segment_id}",
        f"/documents/{document_id}/segments/{segment_id}/audio",
        f"/documents/{document_id}/segments/{segment_id}/audio/manifest",
        f"/documents/{document_id}/progress",
        f"/documents/{document_id}/bookmarks",
        f"/documents/{document_id}/file",
    ):
        assert client.get(path, headers=intruder).status_code == 404, path

    assert (
        client.patch(
            f"/documents/{document_id}",
            json={"title": "mine now"},
            headers=intruder,
        ).status_code
        == 404
    )

    assert (
        client.put(
            f"/documents/{document_id}/progress",
            json={"segment_id": segment_id},
            headers=intruder,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/documents/{document_id}/bookmarks",
            json={"segment_id": segment_id},
            headers=intruder,
        ).status_code
        == 404
    )
    assert client.delete(f"/documents/{document_id}", headers=intruder).status_code == 404


def test_another_reader_cannot_read_your_job(client: TestClient, prepared_document) -> None:
    document_id = prepared_document["document_id"]
    job_id = prepared_document["job"]["job_id"]
    path = f"/documents/{document_id}/jobs/{job_id}"
    assert client.get(path, headers=as_reader(client, READER)).status_code == 200
    assert client.get(path, headers=as_reader(client, OTHER_READER)).status_code == 404


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _first_segment(client: TestClient, document_id: str) -> dict:
    page = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    return page["segments"][0]


def test_a_page_returns_its_segments_in_order(client: TestClient, prepared_document) -> None:
    page = client.get(
        f"/documents/{prepared_document['document_id']}/pages/0", headers=as_reader(client)
    ).json()
    assert page["page_index"] == 0
    assert [s["index"] for s in page["segments"]] == sorted(s["index"] for s in page["segments"])
    assert page["segments"][0]["display_text"]


def test_a_segment_carries_what_a_reader_and_a_reviewer_each_need(
    client: TestClient, prepared_document
) -> None:
    """Display text for the eye and highlighting, spoken text for review.

    The romanised model input is deliberately not exposed: it is meaningful only
    to the synthesiser, and publishing it invites someone to display or index it.
    """
    segment = _first_segment(client, prepared_document["document_id"])
    assert segment["display_text"]
    assert segment["spoken_text"]
    assert "model_text" not in segment
    assert segment["boxes"]


def test_a_page_announces_what_could_not_be_read(client: TestClient) -> None:
    """These are ordinary states of a real book, not errors.

    A reader who cannot see the page needs them in the payload so an interface
    can announce them.
    """
    response = upload(client, build_pdf([legacy_page("DL-Manel")]))
    document_id = response.json()["document_id"]
    page = client.get(f"/documents/{document_id}/pages/0", headers=as_reader(client)).json()
    assert page["quality"] == "undecodable"
    assert page["segments"] == []
    assert any("legacy" in note for note in page["notes"])


def test_asking_for_a_page_before_preparation_finishes_says_so() -> None:
    """409 with the job state, not a 500 and not an empty page.

    The in-flight state is built directly: an accepted upload with a queued job
    and nothing extracted yet. This used to be faked by clearing the in-process
    cache, which stopped meaning "not prepared" once prepared documents were
    written to the store — and a test that fakes a state the application can no
    longer be in tests nothing.
    """
    deps = Deps(store=InMemoryStore(), run_in_background=False)
    client = TestClient(create_app(deps))
    document = deps.store.put_document(
        Document(document_id=new_id("doc"), owner=READER, filename="book.pdf", size_bytes=2048)
    )
    deps.store.put_job(
        Job(
            job_id=new_id("job"),
            document_id=document.document_id,
            owner=READER,
            kind="prepare",
        )
    )

    page = client.get(f"/documents/{document.document_id}/pages/0", headers=as_reader(client))

    assert page.status_code == 409
    assert "not ready" in page.json()["detail"]
    # And it names the job state, so a reader is told "still working" rather
    # than left to guess whether it broke.
    assert "queued" in page.json()["detail"]


def test_a_missing_page_is_a_404(client: TestClient, prepared_document) -> None:
    response = client.get(
        f"/documents/{prepared_document['document_id']}/pages/99", headers=as_reader(client)
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------


def test_audio_comes_back_as_playable_wav(client: TestClient, prepared_document) -> None:
    document_id = prepared_document["document_id"]
    segment = _first_segment(client, document_id)
    response = client.get(
        f"/documents/{document_id}/segments/{segment['segment_id']}/audio",
        headers=as_reader(client),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"

    with wave.open(io.BytesIO(response.content)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getnframes() > 0


def test_placeholder_audio_says_it_is_a_placeholder(client: TestClient, prepared_document) -> None:
    """CLAUDE.md: mock audio must never be presented as real model output.

    A listener cannot tell a tone from speech they were not expecting, so the
    answer travels with the audio rather than being available on request.
    """
    document_id = prepared_document["document_id"]
    segment = _first_segment(client, document_id)
    response = client.get(
        f"/documents/{document_id}/segments/{segment['segment_id']}/audio",
        headers=as_reader(client),
    )
    assert response.headers[REAL_MODEL_HEADER] == "false"


def test_the_manifest_reports_what_produced_the_audio(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    path = f"/documents/{document_id}/segments/{segment_id}/audio/manifest"

    before = client.get(path, headers=as_reader(client)).json()
    assert before["generated"] is False
    assert before["real_model"] is False

    client.get(f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(client))
    after = client.get(path, headers=as_reader(client)).json()
    assert after["generated"] is True
    assert after["voice_id"].startswith("development-")
    assert after["duration_seconds"] > 0
    assert after["cache_key"] == before["cache_key"]


def test_audio_is_generated_once_and_then_served_from_cache(
    client: TestClient, prepared_document
) -> None:
    """Prefetch and playback ask for the same segment constantly."""
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    path = f"/documents/{document_id}/segments/{segment_id}/audio"

    calls: list[str] = []
    deps: Deps = client.app.state.deps
    original = deps.adapter.synthesize

    def counting(*args, **kwargs):
        calls.append(args[0] if args else "")
        return original(*args, **kwargs)

    deps.adapter.synthesize = counting  # type: ignore[method-assign]
    try:
        first = client.get(path, headers=as_reader(client))
        second = client.get(path, headers=as_reader(client))
    finally:
        deps.adapter.synthesize = original  # type: ignore[method-assign]

    assert first.content == second.content
    assert len(calls) == 1


def test_cached_audio_is_still_private(client: TestClient, prepared_document) -> None:
    """CLAUDE.md: keep private audio access-controlled even when it is cached."""
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    path = f"/documents/{document_id}/segments/{segment_id}/audio"

    assert client.get(path, headers=as_reader(client, READER)).status_code == 200
    assert client.get(path, headers=as_reader(client, OTHER_READER)).status_code == 404


# --------------------------------------------------------------------------
# Stopping and coming back
# --------------------------------------------------------------------------


def test_a_reading_position_can_be_saved_and_read_back(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]

    saved = client.put(
        f"/documents/{document_id}/progress",
        json={"segment_id": segment_id, "offset_seconds": 2.5},
        headers=as_reader(client),
    )
    assert saved.status_code == 200

    read_back = client.get(f"/documents/{document_id}/progress", headers=as_reader(client)).json()
    assert read_back["segment_id"] == segment_id
    assert read_back["offset_seconds"] == 2.5
    assert read_back["stale"] is False


def test_a_position_records_the_version_it_was_saved_against(
    client: TestClient, prepared_document
) -> None:
    """Corrected text is a different document.

    Dropping the reader at the same segment id in changed text would put them
    somewhere they never were, so the position carries the version and the
    response says whether it still matches.
    """
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    client.put(
        f"/documents/{document_id}/progress",
        json={"segment_id": segment_id},
        headers=as_reader(client),
    )

    deps: Deps = client.app.state.deps
    from dataclasses import replace

    document = deps.store.get_document(document_id, READER)
    deps.store.put_document(replace(document, version="a-later-version"))

    read_back = client.get(f"/documents/{document_id}/progress", headers=as_reader(client)).json()
    assert read_back["stale"] is True


def test_a_position_must_name_a_segment_that_exists(client: TestClient, prepared_document) -> None:
    response = client.put(
        f"/documents/{prepared_document['document_id']}/progress",
        json={"segment_id": "not-a-segment"},
        headers=as_reader(client),
    )
    assert response.status_code == 404


def test_no_saved_position_is_a_404_rather_than_an_empty_one(
    client: TestClient, prepared_document
) -> None:
    response = client.get(
        f"/documents/{prepared_document['document_id']}/progress", headers=as_reader(client)
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Deletion
# --------------------------------------------------------------------------


def test_deleting_removes_the_document_and_everything_derived_from_it(
    client: TestClient, prepared_document
) -> None:
    """CLAUDE.md requires deletion to remove derived text, audio and caches.

    Anything left behind is private content that outlived the reader's decision
    to delete it.
    """
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    client.get(f"/documents/{document_id}/segments/{segment_id}/audio", headers=as_reader(client))
    client.put(
        f"/documents/{document_id}/progress",
        json={"segment_id": segment_id},
        headers=as_reader(client),
    )
    client.post(
        f"/documents/{document_id}/bookmarks",
        json={"segment_id": segment_id},
        headers=as_reader(client),
    )

    deps: Deps = client.app.state.deps
    from sinhala_reader import preparation

    assert client.delete(f"/documents/{document_id}", headers=as_reader(client)).status_code == 204

    assert deps.store.get_document(document_id, READER) is None
    assert deps.store.get_source(document_id) is None
    assert deps.store.get_progress(document_id, READER) is None
    assert deps.store.jobs_for(document_id, READER) == []
    assert preparation.get_prepared(deps.store, document_id) is None
    assert deps.store.list_bookmarks(document_id, READER) == []
    assert deps.store._audio == {}


def test_deleting_something_that_is_not_yours_does_nothing(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    intruder = as_reader(client, OTHER_READER)
    assert client.delete(f"/documents/{document_id}", headers=intruder).status_code == 404
    assert client.get(f"/documents/{document_id}", headers=as_reader(client)).status_code == 200


def test_a_segment_says_what_kind_of_thing_it_is(client, prepared_document) -> None:
    """Role and level have to reach the interface, or the structure work is invisible.

    Somebody listening cannot see that what they are hearing is a caption rather
    than the next sentence of the paragraph, so the interface has to be able to
    tell them, which means the API has to say.
    """
    page = client.get(
        f"/documents/{prepared_document['document_id']}/pages/0", headers=as_reader(client)
    ).json()
    assert page["segments"]
    for segment in page["segments"]:
        assert "role" in segment
        assert "level" in segment

    # The deterministic path classifies nothing, and says exactly that rather
    # than claiming everything is a paragraph. A page nobody has classified and
    # a page classified as prose are different facts.
    assert {s["role"] for s in page["segments"]} == {"unknown"}
    assert all(s["level"] is None for s in page["segments"])


# --------------------------------------------------------------------------
# The original file, and the reader's own name for it
# --------------------------------------------------------------------------


def test_the_uploaded_pdf_comes_back_byte_for_byte(client: TestClient, book: bytes) -> None:
    """The workspace shows the original page beside the extracted text.

    Byte-for-byte matters more than it looks: the browser renders these bytes
    with pdf.js, and a response that re-encoded or truncated the file would
    show a broken page rather than fail.
    """
    document_id = upload(client, book).json()["document_id"]
    response = client.get(f"/documents/{document_id}/file", headers=as_reader(client))

    assert response.status_code == 200
    assert response.content == book
    assert response.headers["content-type"] == "application/pdf"
    # A shared machine's disk cache is not a place for somebody's textbook.
    assert "no-store" in response.headers["cache-control"]


def test_a_book_can_be_renamed_without_losing_what_was_uploaded(
    client: TestClient, book: bytes
) -> None:
    document_id = upload(client, book, name="scan_final_v2.pdf").json()["document_id"]

    renamed = client.patch(
        f"/documents/{document_id}",
        json={"title": "ඉතිහාසය 11 ශ්‍රේණිය"},
        headers=as_reader(client),
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "ඉතිහාසය 11 ශ්‍රේණිය"
    # The filename is what was actually uploaded. A label must not destroy it.
    assert renamed.json()["filename"] == "scan_final_v2.pdf"

    listed = client.get("/documents", headers=as_reader(client)).json()
    assert listed[0]["title"] == "ඉතිහාසය 11 ශ්‍රේණිය"


def test_clearing_a_title_falls_back_to_the_filename(client: TestClient, book: bytes) -> None:
    """Blank is "I have no name for this", not a title made of spaces.

    Storing the spaces would give the library a card with no heading, which
    looks like a bug and reads as nothing at all.
    """
    document_id = upload(client, book, name="book.pdf").json()["document_id"]
    client.patch(f"/documents/{document_id}", json={"title": "named"}, headers=as_reader(client))

    cleared = client.patch(
        f"/documents/{document_id}", json={"title": "   "}, headers=as_reader(client)
    )
    assert cleared.status_code == 200
    assert cleared.json()["title"] is None
    assert cleared.json()["filename"] == "book.pdf"


def test_the_library_reports_where_each_book_was_left(
    client: TestClient, prepared_document
) -> None:
    """One request, every progress bar.

    A request per card is a request per book on a student's phone data, so the
    position rides along with the list.
    """
    document_id = prepared_document["document_id"]
    before = client.get("/documents", headers=as_reader(client)).json()
    assert before[0]["reading"] is None

    segment = _first_segment(client, document_id)
    client.put(
        f"/documents/{document_id}/progress",
        json={"segment_id": segment["segment_id"], "offset_seconds": 2.5},
        headers=as_reader(client),
    )

    after = client.get("/documents", headers=as_reader(client)).json()
    reading = after[0]["reading"]
    assert reading is not None
    assert reading["segment_id"] == segment["segment_id"]
    # Resolved at save time, so the library never loads a prepared document.
    assert reading["segment_index"] == segment["index"]
    assert reading["stale"] is False


def test_another_reader_never_appears_in_your_reading_positions(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    segment_id = _first_segment(client, document_id)["segment_id"]
    client.put(
        f"/documents/{document_id}/progress",
        json={"segment_id": segment_id},
        headers=as_reader(client, READER),
    )

    # The intruder has no documents at all, so the merge must not leak a
    # position keyed by a document id they cannot see.
    assert client.get("/documents", headers=as_reader(client, OTHER_READER)).json() == []
