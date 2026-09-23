"""What structure changes about the text a reader actually hears.

Everything here is the difference between the deterministic path, which is what
shipped before, and a page whose blocks have roles.
"""

from __future__ import annotations

from pdf_fixtures import Page, Text, build_pdf

from sinhala_documents.blocks import Block
from sinhala_documents.model import QualityState
from sinhala_documents.pdf_extract import extract_document
from sinhala_documents.pipeline import prepare_document, prepare_pages
from sinhala_documents.structure import BlockRole
from sinhala_documents.structuring import DeterministicStructure, StructureAdapter

HEADING = "1.1 කාර්මික විප්ලවය"
BODY = "කාර්මික විප්ලවය ඇරඹිණි."
CAPTION = "රූපය 1.1 - කපු යන්ත්‍රය"


def _pdf() -> bytes:
    return build_pdf([Page((Text(HEADING, y=700), Text(BODY, y=680), Text(CAPTION, y=660)))])


def _extraction():
    return extract_document(_pdf())


class Structured(StructureAdapter):
    """Says what the page is, and nothing about what it says."""

    @property
    def version(self) -> str:
        return "fake-structure-1"

    def blocks_for(self, page_text: str) -> tuple[Block, ...]:
        return (
            Block(BlockRole.HEADING, HEADING, level=2),
            Block(BlockRole.PARAGRAPH, BODY),
            Block(BlockRole.CAPTION, CAPTION),
        )


class Unplaceable(StructureAdapter):
    """Returns a block that verifies but cannot be found in the page."""

    @property
    def version(self) -> str:
        return "unplaceable-1"

    def blocks_for(self, page_text: str) -> tuple[Block, ...]:
        # Same characters, scrambled order: the character count matches, so it
        # survives verification, and no block can be located.
        return (Block(BlockRole.PARAGRAPH, page_text[::-1]),)


def test_the_caption_becomes_its_own_segment() -> None:
    """The defect this whole branch exists for.

    Read in place, the caption interrupts the sentence beside it, and a listener
    cannot see that it happened.
    """
    (page,) = prepare_pages(_extraction(), structure=Structured())
    captions = [s for s in page.segments if s.role is BlockRole.CAPTION]
    assert captions
    assert all(BODY not in s.display_text for s in captions)


def test_a_heading_number_is_not_read_as_a_decimal() -> None:
    (page,) = prepare_pages(_extraction(), structure=Structured())
    heading = next(s for s in page.segments if s.role is BlockRole.HEADING)
    assert heading.level == 2
    assert "දශම" not in heading.spoken_text


def test_the_same_page_without_structure_still_reads_it_as_a_decimal() -> None:
    """The comparison that shows the role is doing the work, not the text."""
    (page,) = prepare_pages(_extraction())
    assert any("දශම" in s.spoken_text for s in page.segments)
    assert all(s.role is BlockRole.UNKNOWN for s in page.segments)


def test_every_segment_is_still_text_from_the_page() -> None:
    """A block supplies a role and never its text.

    The text segmented is the page's own slice, so a reader hears the characters
    we extracted even when the structure came from a model.
    """
    extraction = _extraction()
    page_text = extraction.pages[0].readable_text
    (page,) = prepare_pages(extraction, structure=Structured())
    for segment in page.segments:
        assert segment.display_text in page_text


def test_offsets_still_point_into_the_page_so_boxes_survive() -> None:
    """Segment offsets are within a block; the boxes are indexed by the page."""
    (page,) = prepare_pages(_extraction(), structure=Structured())
    assert all(segment.boxes for segment in page.segments)


def test_an_unplaceable_structuring_falls_back_rather_than_losing_text() -> None:
    """A block nobody can place would take its text out of the document."""
    extraction = _extraction()
    (structured,) = prepare_pages(extraction, structure=Unplaceable())
    (plain,) = prepare_pages(extraction)
    assert [s.display_text for s in structured.segments] == [s.display_text for s in plain.segments]


def test_a_page_whose_structure_failed_is_marked_for_review() -> None:
    class Invents(StructureAdapter):
        @property
        def version(self) -> str:
            return "invents-1"

        def blocks_for(self, page_text: str) -> tuple[Block, ...]:
            return (Block(BlockRole.PARAGRAPH, "මෙය පිටුවේ නොතිබූ දෙයකි"),)

    (page,) = prepare_pages(_extraction(), structure=Invents())
    assert page.quality is QualityState.NEEDS_REVIEW
    assert page.notes
    assert page.segments, "the page must still be readable"


def test_prepare_document_takes_a_structure_adapter_too() -> None:
    """The public entry point, which is what the API calls.

    prepare_pages taking one and prepare_document not would mean the whole
    feature was unreachable from the only function anything outside this package
    uses.
    """
    pdf = build_pdf([Page((Text(HEADING, y=700), Text(BODY, y=680), Text(CAPTION, y=660)))])
    document = prepare_document(pdf, structure=Structured())
    assert any(s.role is BlockRole.CAPTION for s in document.segments)
    assert any(s.role is BlockRole.HEADING for s in document.segments)


class TestDocumentVersion:
    """Structure is provenance, so it belongs in the document version.

    CLAUDE.md requires the structure provider, model and prompt "in the document
    version and in every affected cache key". The version is what audio is cached
    under, so without this, turning structure on - or revising its prompt - left
    the old audio in place, spoken from text the new structuring would not write.
    """

    def test_a_structured_document_has_a_different_version(self) -> None:
        plain = prepare_document(_pdf())
        structured = prepare_document(_pdf(), structure=Structured())

        assert plain.version != structured.version

    def test_a_revised_prompt_is_a_new_version(self) -> None:
        class Revised(Structured):
            @property
            def version(self) -> str:
                return "fake-structure-2"

        first = prepare_document(_pdf(), structure=Structured())
        revised = prepare_document(_pdf(), structure=Revised())

        assert first.version != revised.version

    def test_the_same_structuring_gives_the_same_version(self) -> None:
        """Or every preparation would miss the cache it just filled."""
        first = prepare_document(_pdf(), structure=Structured())
        again = prepare_document(_pdf(), structure=Structured())

        assert first.version == again.version

    def test_deterministic_structure_keeps_every_existing_version(self) -> None:
        """Naming the default must change nothing.

        Every book prepared before this was prepared deterministically. Were the
        default written into the version, all of them - and all their cached
        audio - would be invalidated to record something that was always true.
        """
        default = prepare_document(_pdf())
        named = prepare_document(_pdf(), structure=DeterministicStructure())

        assert default.version == named.version
