"""Bookmarks: places a reader chose, and can get back to without seeing them.

Progress is written *for* a reader — where they stopped. A bookmark is a
decision, and the tests here are mostly about what that decision costs someone
navigating the list by ear:

* pressing the button twice must not leave two identical entries
* the list must run in the order of the book, not the order of the pressing
* a bookmark into text that has changed must say so, rather than read out a
  sentence that is not the one that was marked
"""

from __future__ import annotations

import dataclasses

from conftest import OTHER_READER, READER, as_reader
from fastapi.testclient import TestClient

from sinhala_reader import Deps, create_app
from sinhala_reader.storage import Bookmark, Document, InMemoryStore, Job, new_id


def segments_of(client: TestClient, document_id: str, page: int = 0) -> list[dict]:
    response = client.get(f"/documents/{document_id}/pages/{page}", headers=as_reader(client))
    assert response.status_code == 200, response.text
    return response.json()["segments"]


def add(
    client: TestClient,
    document_id: str,
    segment_id: str,
    note: str | None = None,
    owner: str = READER,
):
    body: dict = {"segment_id": segment_id}
    if note is not None:
        body["note"] = note
    return client.post(
        f"/documents/{document_id}/bookmarks", json=body, headers=as_reader(client, owner)
    )


def listed(client: TestClient, document_id: str, owner: str = READER) -> list[dict]:
    response = client.get(f"/documents/{document_id}/bookmarks", headers=as_reader(client, owner))
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# Marking a place
# --------------------------------------------------------------------------


def test_a_bookmark_comes_back_with_the_sentence_it_marks(
    client: TestClient, prepared_document
) -> None:
    """A list of identifiers is not a list anybody can choose from."""
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]

    response = add(client, document_id, segment["segment_id"], note="start here")

    assert response.status_code == 201
    body = response.json()
    assert body["segment_id"] == segment["segment_id"]
    assert body["note"] == "start here"
    assert body["display_text"] == segment["display_text"]
    assert body["page_index"] == segment["page_index"]
    assert body["segment_found"] is True
    assert body["stale"] is False


def test_a_note_is_optional(client: TestClient, prepared_document) -> None:
    """Marking the place is the feature. Describing it is extra."""
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]

    response = add(client, document_id, segment["segment_id"])

    assert response.status_code == 201
    assert response.json()["note"] is None


def test_a_note_of_only_spaces_is_no_note(client: TestClient, prepared_document) -> None:
    """Otherwise a list item announces a blank where a description should be."""
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]

    assert add(client, document_id, segment["segment_id"], note="   ").json()["note"] is None


def test_a_note_longer_than_a_label_is_refused(client: TestClient, prepared_document) -> None:
    """A bookmark list is listened to. It is not somewhere to paste a document."""
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]

    response = add(client, document_id, segment["segment_id"], note="x" * 281)

    assert response.status_code == 422


def test_marking_the_same_sentence_twice_edits_rather_than_duplicates(
    client: TestClient, prepared_document
) -> None:
    """The button gives no feedback a blind reader can see.

    So the second press has to be harmless: one entry, the newer note, the same
    id — not a duplicate to be found and deleted twice.
    """
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    first = add(client, document_id, segment["segment_id"], note="here").json()

    again = add(client, document_id, segment["segment_id"], note="here, really")

    assert again.status_code == 200, "nothing was created, so this is not a 201"
    assert again.json()["bookmark_id"] == first["bookmark_id"]
    assert again.json()["note"] == "here, really"
    assert len(listed(client, document_id)) == 1


def test_a_segment_that_is_not_in_the_book_cannot_be_bookmarked(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]

    assert add(client, document_id, "seg_invented").status_code == 404


def test_a_document_that_is_not_ready_cannot_be_bookmarked() -> None:
    """There is nothing to point at yet, and no way to check the id is real.

    The in-flight state is built directly — an accepted upload with a queued job
    and nothing extracted — rather than faked by emptying a cache.
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

    response = add(client, document.document_id, "seg_0")

    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


# --------------------------------------------------------------------------
# Getting back to it
# --------------------------------------------------------------------------


def test_the_list_runs_in_the_order_of_the_book(client: TestClient, prepared_document) -> None:
    """Not the order they were made.

    This is a way of moving through a document. A list that jumps backwards is
    one a reader has to hold in their head instead of stepping down.
    """
    document_id = prepared_document["document_id"]
    segments = segments_of(client, document_id)
    assert len(segments) >= 2, "the fixture book should have more than one sentence"
    add(client, document_id, segments[-1]["segment_id"])
    add(client, document_id, segments[0]["segment_id"])

    order = [b["segment_id"] for b in listed(client, document_id)]

    assert order == [segments[0]["segment_id"], segments[-1]["segment_id"]]


def test_the_list_spans_the_whole_book_not_one_page(client: TestClient, prepared_document) -> None:
    """Bookmarks are how a reader moves between chapters, so pages cannot bound them."""
    document_id = prepared_document["document_id"]
    first_page = segments_of(client, document_id, 0)
    second_page = segments_of(client, document_id, 1)
    add(client, document_id, second_page[0]["segment_id"])
    add(client, document_id, first_page[0]["segment_id"])

    order = [b["segment_id"] for b in listed(client, document_id)]

    assert order == [first_page[0]["segment_id"], second_page[0]["segment_id"]]


def test_deleting_a_bookmark_leaves_the_rest(client: TestClient, prepared_document) -> None:
    document_id = prepared_document["document_id"]
    segments = segments_of(client, document_id)
    keep = add(client, document_id, segments[0]["segment_id"]).json()
    drop = add(client, document_id, segments[1]["segment_id"]).json()

    response = client.delete(
        f"/documents/{document_id}/bookmarks/{drop['bookmark_id']}", headers=as_reader(client)
    )

    assert response.status_code == 204
    assert [b["bookmark_id"] for b in listed(client, document_id)] == [keep["bookmark_id"]]


def test_deleting_a_bookmark_that_is_not_there_is_a_404(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]

    response = client.delete(
        f"/documents/{document_id}/bookmarks/bmk_invented", headers=as_reader(client)
    )

    assert response.status_code == 404


def test_the_place_can_be_marked_again_after_being_removed(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    bookmark = add(client, document_id, segment["segment_id"]).json()
    client.delete(
        f"/documents/{document_id}/bookmarks/{bookmark['bookmark_id']}",
        headers=as_reader(client),
    )

    assert add(client, document_id, segment["segment_id"]).status_code == 201


# --------------------------------------------------------------------------
# When the book changes underneath them
# --------------------------------------------------------------------------


def test_a_bookmark_made_against_older_text_says_so(
    client: TestClient, deps: Deps, prepared_document
) -> None:
    """Corrected text is a different document.

    The sentence at that id may not be the sentence that was marked, and a
    reader has no way to notice that for themselves.
    """
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    add(client, document_id, segment["segment_id"])

    document = deps.store.get_document(document_id, READER)
    assert document is not None
    deps.store.put_document(dataclasses.replace(document, version="a-later-version"))

    assert listed(client, document_id)[0]["stale"] is True


def test_a_bookmark_into_text_that_is_gone_is_listed_but_not_described(
    client: TestClient, deps: Deps, prepared_document
) -> None:
    """Dropping it silently would leave a reader wondering what they had marked.

    Describing it with whatever sentence now holds that place would be worse.
    """
    document_id = prepared_document["document_id"]
    document = deps.store.get_document(document_id, READER)
    assert document is not None and document.version is not None
    deps.store.put_bookmark(
        Bookmark(
            bookmark_id="bmk_orphan",
            document_id=document_id,
            owner=READER,
            document_version=document.version,
            segment_id="seg_that_was_removed",
            note="chapter three",
        )
    )

    orphan = next(b for b in listed(client, document_id) if b["bookmark_id"] == "bmk_orphan")

    assert orphan["segment_found"] is False
    assert orphan["display_text"] is None
    assert orphan["page_index"] is None
    assert orphan["note"] == "chapter three"


def test_what_cannot_be_placed_goes_last(client: TestClient, deps: Deps, prepared_document) -> None:
    """A bookmark with no position must not land at an arbitrary point in the list."""
    document_id = prepared_document["document_id"]
    segments = segments_of(client, document_id)
    document = deps.store.get_document(document_id, READER)
    assert document is not None and document.version is not None
    deps.store.put_bookmark(
        Bookmark(
            bookmark_id="bmk_orphan",
            document_id=document_id,
            owner=READER,
            document_version=document.version,
            segment_id="seg_that_was_removed",
        )
    )
    add(client, document_id, segments[0]["segment_id"])

    assert [b["bookmark_id"] for b in listed(client, document_id)][-1] == "bmk_orphan"


# --------------------------------------------------------------------------
# Whose bookmarks they are
# --------------------------------------------------------------------------


def test_another_reader_sees_no_bookmarks_and_no_document(
    client: TestClient, prepared_document
) -> None:
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    add(client, document_id, segment["segment_id"])

    response = client.get(
        f"/documents/{document_id}/bookmarks", headers=as_reader(client, OTHER_READER)
    )

    # The same answer as for a document that does not exist: a 403 on an id
    # would confirm that the id belongs to somebody.
    assert response.status_code == 404


def test_another_reader_cannot_delete_one(client: TestClient, prepared_document) -> None:
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    bookmark = add(client, document_id, segment["segment_id"]).json()

    response = client.delete(
        f"/documents/{document_id}/bookmarks/{bookmark['bookmark_id']}",
        headers=as_reader(client, OTHER_READER),
    )

    assert response.status_code == 404
    assert len(listed(client, document_id)) == 1


def test_deleting_the_document_takes_the_bookmarks_with_it(
    client: TestClient, deps: Deps, prepared_document
) -> None:
    """CLAUDE.md: deletion removes everything derived, not just the row."""
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    bookmark = add(client, document_id, segment["segment_id"]).json()

    client.delete(f"/documents/{document_id}", headers=as_reader(client))

    assert deps.store.get_bookmark(bookmark["bookmark_id"], READER) is None


# --------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------


def test_a_reader_cannot_fill_a_document_with_bookmarks(
    client: TestClient, monkeypatch, prepared_document
) -> None:
    """A quota, so a bookmark list cannot become a place to store text."""
    from sinhala_reader import app as app_module

    monkeypatch.setattr(app_module, "MAX_BOOKMARKS", 1)
    document_id = prepared_document["document_id"]
    segments = segments_of(client, document_id)
    assert add(client, document_id, segments[0]["segment_id"]).status_code == 201

    response = add(client, document_id, segments[1]["segment_id"])

    assert response.status_code == 409
    assert "Remove one" in response.json()["detail"]


def test_the_quota_does_not_stop_editing_one_that_is_already_there(
    client: TestClient, monkeypatch, prepared_document
) -> None:
    """Being at the limit must not make the bookmarks already there unusable."""
    from sinhala_reader import app as app_module

    monkeypatch.setattr(app_module, "MAX_BOOKMARKS", 1)
    document_id = prepared_document["document_id"]
    segment = segments_of(client, document_id)[0]
    add(client, document_id, segment["segment_id"], note="first")

    response = add(client, document_id, segment["segment_id"], note="second")

    assert response.status_code == 200
    assert response.json()["note"] == "second"
