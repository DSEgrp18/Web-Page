"""The join between extraction and speech.

Two packages that had never met. Everything here is about the seam: what
survives it, what must not cross it, and what a reader can still point at
afterwards.
"""

from __future__ import annotations

from pdf_fixtures import LEGACY_LINE, Page, Text, build_pdf, legacy_page, sinhala_page

from sinhala_documents import prepare_document
from sinhala_documents.pipeline import PIPELINE_VERSION, _document_version


def prepared(*pages: Page, **kwargs):
    return prepare_document(build_pdf(list(pages)), **kwargs)


# --------------------------------------------------------------------------
# What reaches the synthesiser
# --------------------------------------------------------------------------


def test_a_page_becomes_playable_segments() -> None:
    document = prepared(sinhala_page())
    assert document.segments
    for segment in document.segments:
        assert segment.display_text
        assert segment.model_text


def test_all_three_text_stages_survive_the_join() -> None:
    """Display for the eye, spoken for review, model for the synthesiser.

    Losing any one of them here is unrecoverable downstream: a pronunciation
    complaint cannot be diagnosed without the spoken text, and highlighting
    cannot work without the display text.
    """
    document = prepared(Page(blocks=(Text("පිටුව 42 බලන්න.", y=700),)))
    segment = document.segments[0]
    assert segment.display_text == "පිටුව 42 බලන්න."
    assert segment.spoken_text == "පිටුව හතළිස් දෙක බලන්න."
    assert segment.model_text == "pituva hathalis dheka balanna."


def test_undecodable_text_never_reaches_the_synthesiser() -> None:
    """Filtered at the join, not downstream.

    Anything that gets past here is something a listener will hear.
    """
    document = prepared(legacy_page("DL-Manel"))
    assert document.segments == ()


def test_decoded_legacy_text_does_reach_it() -> None:
    """FM-Abhaya converts, so it is narratable like any other Sinhala."""
    document = prepared(legacy_page("ABCDEF+FMAbhaya"))
    assert document.segments
    assert LEGACY_LINE not in document.segments[0].display_text


def test_a_readable_page_beside_an_unreadable_one_still_plays() -> None:
    """CLAUDE.md: allow access to valid sections rather than failing the book."""
    document = prepared(sinhala_page(), legacy_page("DL-Manel"))
    assert [page.has_audio for page in document.pages] == [True, False]
    assert all(segment.page_index == 0 for segment in document.segments)


def test_a_page_with_nothing_to_read_is_reported() -> None:
    document = prepared(sinhala_page(), Page(images=1))
    assert any("read aloud" in note for note in document.notes)


# --------------------------------------------------------------------------
# Where a segment is
# --------------------------------------------------------------------------


def test_every_segment_names_the_page_it_came_from() -> None:
    """A citation has to name one page, so a segment may only belong to one."""
    document = prepared(sinhala_page(), sinhala_page())
    assert {segment.page_index for segment in document.segments} == {0, 1}


def test_segments_carry_the_printed_page_label() -> None:
    document = prepare_document(build_pdf([sinhala_page()], labels=[(0, "r")]))
    assert document.segments[0].page_label == "i"


def test_a_segment_keeps_the_boxes_of_the_lines_it_covers() -> None:
    """Sentence highlighting draws these, and they cannot be recovered later."""
    document = prepared(sinhala_page())
    segment = document.segments[0]
    assert segment.boxes
    assert segment.box is not None
    assert segment.box.width > 0


def test_a_segment_spanning_two_lines_carries_both() -> None:
    """A sentence that wraps is one segment drawn across two lines.

    Real pages are mostly this: the sentence, not the line, is the unit a
    listener follows, and highlighting has to cover every line it touches.
    """
    document = prepared(
        Page(
            blocks=(
                Text("පොත් කියවීම මගින් දැනුම", y=700),
                Text("වර්ධනය වේ.", y=680),
            )
        )
    )
    segment = document.segments[0]
    assert segment.display_text.splitlines() == ["පොත් කියවීම මගින් දැනුම", "වර්ධනය වේ."]
    assert len(segment.boxes) == 2
    assert segment.box.top == min(box.top for box in segment.boxes)


def test_indexes_run_across_the_whole_document() -> None:
    """Resume stores a position in the document, not in a page."""
    document = prepared(sinhala_page(), sinhala_page())
    assert [segment.index for segment in document.segments] == list(range(len(document.segments)))


# --------------------------------------------------------------------------
# Identity, and what should invalidate audio
# --------------------------------------------------------------------------


def test_the_same_pdf_prepares_to_the_same_version() -> None:
    pdf = build_pdf([sinhala_page()])
    assert prepare_document(pdf).version == prepare_document(pdf).version


def test_a_different_pdf_prepares_to_a_different_version() -> None:
    assert prepared(sinhala_page()).version != prepared(legacy_page()).version


def test_the_version_covers_everything_that_transforms_the_text() -> None:
    """A change to the converter or the number words changes what is heard.

    Serving audio generated under the old ones would be a silent regression, so
    those versions have to be part of document identity — not just the bytes.
    """
    assert _document_version("abc") != _document_version("abd")

    import sinhala_documents.pipeline as pipeline

    original = pipeline.PIPELINE_VERSION
    try:
        pipeline.PIPELINE_VERSION = "99"
        assert _document_version("abc") != original and pipeline.PIPELINE_VERSION == "99"
        changed = _document_version("abc")
    finally:
        pipeline.PIPELINE_VERSION = original
    assert changed != _document_version("abc")


def test_the_version_does_not_depend_on_which_pages_were_prepared() -> None:
    """One page prepared alone must share cache entries with the whole book.

    Otherwise reading chapter one, then the book, generates every segment of
    chapter one twice.
    """
    pdf = build_pdf([sinhala_page(), sinhala_page()])
    assert prepare_document(pdf, page_indexes=[0]).version == prepare_document(pdf).version


def test_a_segment_prepared_alone_matches_the_one_prepared_with_the_book() -> None:
    pdf = build_pdf([sinhala_page(), sinhala_page()])
    alone = prepare_document(pdf, page_indexes=[1]).segments
    together = [s for s in prepare_document(pdf).segments if s.page_index == 1]
    assert [s.segment_id for s in alone] == [s.segment_id for s in together]


def test_editing_one_page_leaves_the_other_pages_ids_alone() -> None:
    """Otherwise one correction reprocesses the audio for a whole book."""
    first = prepared(sinhala_page(), Page(blocks=(Text("පළමු වාක්‍යය.", y=700),)))
    second = prepared(sinhala_page(), Page(blocks=(Text("දෙවන වාක්‍යය.", y=700),)))
    page_one = lambda doc: [s.segment_id for s in doc.segments if s.page_index == 0]  # noqa: E731
    assert page_one(first) == page_one(second)


def test_segment_ids_are_unique_across_pages() -> None:
    """Two pages with identical text must not collide."""
    document = prepared(sinhala_page(), sinhala_page())
    ids = [segment.segment_id for segment in document.segments]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# Selecting what to prepare
# --------------------------------------------------------------------------


def test_one_section_can_be_prepared_before_the_rest() -> None:
    """A reader starts chapter one while chapter twelve is still processing."""
    pdf = build_pdf([sinhala_page(), sinhala_page(), sinhala_page()])
    document = prepare_document(pdf, page_indexes=[2])
    assert [page.page_index for page in document.pages] == [2]
    assert all(segment.page_index == 2 for segment in document.segments)


def test_a_document_can_be_looked_up_by_segment_and_page() -> None:
    document = prepared(sinhala_page())
    first = document.segments[0]
    assert document.segment(first.segment_id) is first
    assert document.page(0) is document.pages[0]
    assert document.segment("nonsense") is None


def test_the_pipeline_version_is_declared() -> None:
    assert PIPELINE_VERSION
