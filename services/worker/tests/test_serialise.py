"""A prepared document has to come back exactly as it went in.

Not approximately. A serialiser that drops bounding boxes loses the sentence
highlighting a low-vision reader follows, and one that drops ``model_text``
describes audio as having been made from something it was not — while page
counts, quality states and every visible number still look right. Both would be
invisible until somebody noticed the reader had stopped working.

So the central test compares whole documents, not fields, on pages produced by
the real extraction pipeline rather than by hand.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pdf_fixtures import build_pdf, legacy_page, sinhala_page

from sinhala_documents.chapters import Chapter
from sinhala_documents.model import PageKind, QualityState
from sinhala_documents.passages import build_passages
from sinhala_documents.pipeline import ReadableDocument, prepare_document
from sinhala_documents.serialise import (
    FORMAT_VERSION,
    UnreadableFormat,
    from_json,
    to_json,
)
from sinhala_documents.structure import BlockRole


@pytest.fixture
def prepared():
    return prepare_document(build_pdf([sinhala_page(), legacy_page(), sinhala_page()]))


def _structured(document: ReadableDocument) -> ReadableDocument:
    """The same document as if structure inference had found its layout.

    Deterministic structure marks every segment ``UNKNOWN``, which is the
    default, so a document prepared without a provider has no roles to lose.
    That is why the round trip above never noticed them being dropped. These
    roles are the ones a provider assigns, and the ones that change what a
    reader gets.
    """
    segments = document.segments
    assert len(segments) >= 3, "the fixture should produce at least three segments"
    roles = {
        segments[0].segment_id: (BlockRole.HEADING, 1),
        segments[1].segment_id: (BlockRole.RUNNING_HEAD, None),
        segments[-1].segment_id: (BlockRole.CAPTION, None),
    }
    pages = tuple(
        replace(
            page,
            segments=tuple(
                replace(s, role=roles[s.segment_id][0], level=roles[s.segment_id][1])
                if s.segment_id in roles
                else s
                for s in page.segments
            ),
        )
        for page in document.pages
    )
    return replace(document, pages=pages)


class TestRoundTrip:
    def test_the_whole_document_is_identical(self, prepared) -> None:
        assert from_json(to_json(prepared)) == prepared

    def test_twice_is_still_identical(self, prepared) -> None:
        """Reading and writing must not drift; a stored payload gets rewritten."""
        once = to_json(prepared)

        assert to_json(from_json(once)) == once

    def test_boxes_survive_with_their_numbers(self, prepared) -> None:
        """Sentence highlighting is built on these, and they are stored unnamed."""
        original = [s for s in prepared.segments if s.boxes]
        assert original, "the fixture should produce at least one segment with boxes"

        back = from_json(to_json(prepared))

        for before, after in zip(original, [s for s in back.segments if s.boxes], strict=True):
            assert before.boxes == after.boxes

    def test_the_text_the_model_was_given_is_kept_not_recomputed(self, prepared) -> None:
        """Regenerating it under a changed romaniser would misdescribe old audio."""
        payload = json.loads(to_json(prepared))
        stored = payload["pages"][0]["segments"][0]["model_text"]

        assert stored == prepared.pages[0].segments[0].model_text

    def test_enum_values_are_stored_not_python_names(self, prepared) -> None:
        """A renamed Python member must not silently change stored data."""
        payload = json.loads(to_json(prepared))
        page = payload["pages"][0]

        assert page["kind"] in {k.value for k in PageKind}
        assert page["quality"] in {q.value for q in QualityState}

    def test_sinhala_is_stored_as_sinhala(self, prepared) -> None:
        """Not \\u0d85 escapes. A payload somebody may have to read by eye."""
        raw = to_json(prepared)

        assert "\\u0d" not in raw.lower()


class TestChapters:
    def test_chapters_survive_with_their_numbers(self, prepared) -> None:
        with_chapters = replace(
            prepared,
            chapters=(
                Chapter(title="කාර්මික විප්ලවය", page_index=0, number="01"),
                Chapter(title="පෙරවදන", page_index=2, number=None),
            ),
        )

        assert from_json(to_json(with_chapters)) == with_chapters

    def test_none_found_stays_distinct_from_never_looked(self, prepared) -> None:
        """An empty list claims the book has no chapters; ``None`` claims nothing."""
        assert from_json(to_json(replace(prepared, chapters=()))).chapters == ()
        assert from_json(to_json(replace(prepared, chapters=None))).chapters is None

    def test_a_row_written_before_chapters_existed_still_reads(self, prepared) -> None:
        payload = json.loads(to_json(prepared))
        del payload["chapters"]

        assert from_json(json.dumps(payload)).chapters is None


class TestStructure:
    """What structure inference found has to survive being stored.

    Under Celery the worker prepares a book and the API reads it back from the
    database, so a role that is not stored is a role the reader never gets: a
    heading comes back as ``unknown``, the passages lose their sections, and a
    running head is cited as evidence for an answer.
    """

    def test_segment_roles_and_levels_survive(self, prepared) -> None:
        structured = _structured(prepared)

        assert from_json(to_json(structured)) == structured

    def test_passages_rebuilt_after_a_reload_keep_their_sections(self, prepared) -> None:
        structured = _structured(prepared)
        heading = " ".join(structured.segments[0].display_text.split())
        before = build_passages(structured)
        assert any(p.section_path == (heading,) for p in before), "precondition"

        after = build_passages(from_json(to_json(structured)))

        assert after == before

    def test_a_running_head_is_not_cited_after_a_reload(self, prepared) -> None:
        """It repeats on every page, so it would match every question."""
        structured = _structured(prepared)
        running_head = structured.segments[1].segment_id

        reloaded = from_json(to_json(structured))
        cited = {sid for passage in build_passages(reloaded) for sid in passage.segment_ids}

        assert running_head not in cited

    def test_roles_are_stored_as_values(self, prepared) -> None:
        """The same rule as page kinds: a renamed member must not change data."""
        payload = json.loads(to_json(_structured(prepared)))
        stored = [s["role"] for p in payload["pages"] for s in p["segments"] if "role" in s]

        assert stored
        assert set(stored) <= {role.value for role in BlockRole}

    def test_a_document_without_structure_stores_no_roles(self, prepared) -> None:
        """Most books are prepared without a provider, and should not pay for one.

        ``UNKNOWN`` and no level are the defaults, so they are not written.
        """
        raw = to_json(prepared)

        assert '"role"' not in raw
        assert '"level"' not in raw

    def test_a_row_written_before_roles_were_stored_reads_as_unknown(self, prepared) -> None:
        """Older rows never had roles, so ``UNKNOWN`` is what they always were."""
        payload = json.loads(to_json(_structured(prepared)))
        for page in payload["pages"]:
            for segment in page["segments"]:
                segment.pop("role", None)
                segment.pop("level", None)

        back = from_json(json.dumps(payload))

        assert {s.role for s in back.segments} == {BlockRole.UNKNOWN}
        assert {s.level for s in back.segments} == {None}


class TestRefusingWhatItCannotRead:
    def test_an_unknown_format_is_refused_rather_than_guessed(self, prepared) -> None:
        """A half-understood page is worse than an absent one.

        The reader is told the book is ready and then hears the wrong thing,
        with no way to tell that is what happened.
        """
        payload = json.loads(to_json(prepared))
        payload["format"] = FORMAT_VERSION + 1

        with pytest.raises(UnreadableFormat):
            from_json(json.dumps(payload))

    def test_a_payload_with_no_format_is_refused(self, prepared) -> None:
        payload = json.loads(to_json(prepared))
        del payload["format"]

        with pytest.raises(UnreadableFormat):
            from_json(json.dumps(payload))

    @pytest.mark.parametrize("broken", ["", "{}", "[]", "not json at all"])
    def test_rubbish_raises_rather_than_returning_something(self, broken: str) -> None:
        with pytest.raises((UnreadableFormat, ValueError)):
            from_json(broken)


class TestSize:
    def test_a_page_costs_roughly_what_its_text_costs(self, prepared) -> None:
        """A sanity bound, not a benchmark.

        Boxes are stored as bare lists precisely because four numbers per line
        across a whole book is the bulk of the payload. If this ratio ever grows
        a lot, that decision has been undone.
        """
        text = sum(len(segment.display_text) for segment in prepared.segments)
        payload = len(to_json(prepared))

        assert payload < text * 40, f"{payload} bytes for {text} characters of text"
