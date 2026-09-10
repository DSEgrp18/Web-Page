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

import pytest
from pdf_fixtures import build_pdf, legacy_page, sinhala_page

from sinhala_documents.model import PageKind, QualityState
from sinhala_documents.pipeline import prepare_document
from sinhala_documents.serialise import (
    FORMAT_VERSION,
    UnreadableFormat,
    from_json,
    to_json,
)


@pytest.fixture
def prepared():
    return prepare_document(build_pdf([sinhala_page(), legacy_page(), sinhala_page()]))


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
