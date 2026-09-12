"""Passages: the unit a question is answered from.

A segment is one sentence sized for the voice. A passage is evidence. These
assert the ways the two must differ.
"""

from __future__ import annotations

from sinhala_documents.model import PageKind, QualityState
from sinhala_documents.passages import MAX_CHARACTERS, Passage, build_passages
from sinhala_documents.pipeline import ReadableDocument, ReadablePage, ReadableSegment
from sinhala_documents.structure import BlockRole


def _segment(
    text: str,
    *,
    index: int,
    role: BlockRole = BlockRole.PARAGRAPH,
    level: int | None = None,
    page: int = 0,
    label: str | None = "18",
) -> ReadableSegment:
    return ReadableSegment(
        segment_id=f"s{index}",
        index=index,
        page_index=page,
        page_label=label,
        display_text=text,
        spoken_text=text,
        model_text=text,
        boxes=(),
        role=role,
        level=level,
    )


def _document(segments: list[ReadableSegment], version: str = "v1") -> ReadableDocument:
    pages: dict[int, list[ReadableSegment]] = {}
    for segment in segments:
        pages.setdefault(segment.page_index, []).append(segment)
    return ReadableDocument(
        version=version,
        pages=tuple(
            ReadablePage(
                page_index=index,
                page_label=items[0].page_label,
                kind=PageKind.TEXT,
                quality=QualityState.ACCEPTED,
                segments=tuple(items),
                notes=(),
            )
            for index, items in sorted(pages.items())
        ),
        notes=(),
    )


def test_a_passage_gathers_several_segments() -> None:
    """One sentence is not evidence. "ඒ අනුව" is a complete segment."""
    document = _document([_segment(f"වාක්‍ය අංක {n} මෙහි ඇත.", index=n) for n in range(4)])
    (passage,) = build_passages(document)
    assert len(passage.segment_ids) == 4


def test_a_passage_never_crosses_a_heading() -> None:
    """1.1 and 1.2 answer different questions."""
    document = _document(
        [
            _segment("1.1 ආරම්භය", index=0, role=BlockRole.HEADING, level=2),
            _segment("පළමු කොටසේ අන්තර්ගතය.", index=1),
            _segment("1.2 ප්‍රබෝධය", index=2, role=BlockRole.HEADING, level=2),
            _segment("දෙවන කොටසේ අන්තර්ගතය.", index=3),
        ]
    )
    first, second = build_passages(document)
    assert first.section_path == ("1.1 ආරම්භය",)
    assert second.section_path == ("1.2 ප්‍රබෝධය",)
    assert "දෙවන" not in first.text


def test_a_passage_carries_the_headings_above_it() -> None:
    """A citation without a section is a page number the reader must search."""
    document = _document(
        [
            _segment("පළමු පරිච්ඡේදය", index=0, role=BlockRole.HEADING, level=1),
            _segment("1.1 ආරම්භය", index=1, role=BlockRole.HEADING, level=2),
            _segment("අන්තර්ගතය මෙහි ඇත.", index=2),
        ]
    )
    (passage,) = build_passages(document)
    assert passage.section_path == ("පළමු පරිච්ඡේදය", "1.1 ආරම්භය")
    assert passage.section == "පළමු පරිච්ඡේදය › 1.1 ආරම්භය"


def test_a_deeper_heading_does_not_discard_the_chapter_above_it() -> None:
    document = _document(
        [
            _segment("පළමු පරිච්ඡේදය", index=0, role=BlockRole.HEADING, level=1),
            _segment("1.1 ආරම්භය", index=1, role=BlockRole.HEADING, level=2),
            _segment("1.2 ප්‍රබෝධය", index=2, role=BlockRole.HEADING, level=2),
            _segment("අන්තර්ගතය.", index=3),
        ]
    )
    (passage,) = build_passages(document)
    assert passage.section_path == ("පළමු පරිච්ඡේදය", "1.2 ප්‍රබෝධය")


def test_a_new_chapter_clears_the_sections_under_the_old_one() -> None:
    document = _document(
        [
            _segment("පළමු පරිච්ඡේදය", index=0, role=BlockRole.HEADING, level=1),
            _segment("1.1 ආරම්භය", index=1, role=BlockRole.HEADING, level=2),
            _segment("පැරණි අන්තර්ගතය.", index=2),
            _segment("දෙවන පරිච්ඡේදය", index=3, role=BlockRole.HEADING, level=1),
            _segment("නව අන්තර්ගතය.", index=4),
        ]
    )
    _, second = build_passages(document)
    assert second.section_path == ("දෙවන පරිච්ඡේදය",)


def test_a_passage_never_crosses_a_page_because_a_citation_names_one() -> None:
    document = _document(
        [
            _segment("පළමු පිටුවේ.", index=0, page=0, label="18"),
            _segment("දෙවන පිටුවේ.", index=1, page=1, label="19"),
        ]
    )
    first, second = build_passages(document)
    assert (first.page_index, first.page_label) == (0, "18")
    assert (second.page_index, second.page_label) == (1, "19")


def test_a_caption_is_evidence_even_though_it_reads_badly_in_sequence() -> None:
    """Often the only place a date or a name appears."""
    document = _document(
        [
            _segment("ප්‍රධාන අන්තර්ගතය.", index=0),
            _segment("රූපය 1.8 - ජෝර්ජ් ස්ටීවන්සන්", index=1, role=BlockRole.CAPTION),
        ]
    )
    (passage,) = build_passages(document)
    assert "ජෝර්ජ් ස්ටීවන්සන්" in passage.text
    assert BlockRole.CAPTION in passage.roles


def test_running_heads_and_page_numbers_are_not_evidence() -> None:
    """They repeat on every page, so they match everything and distinguish nothing."""
    document = _document(
        [
            _segment("කාර්මික විප්ලවය", index=0, role=BlockRole.RUNNING_HEAD),
            _segment("සැබෑ අන්තර්ගතය.", index=1),
            _segment("18", index=2, role=BlockRole.PAGE_NUMBER),
        ]
    )
    (passage,) = build_passages(document)
    assert passage.text == "සැබෑ අන්තර්ගතය."


def test_a_passage_knows_which_segments_to_play() -> None:
    """A citation a reader cannot hear is not reachable without sight."""
    document = _document([_segment("අන්තර්ගතය.", index=n) for n in range(3)])
    (passage,) = build_passages(document)
    assert passage.segment_ids == ("s0", "s1", "s2")


def test_passages_stay_within_the_maximum() -> None:
    long_sentence = "දිගු වාක්‍යයකි. " * 40
    document = _document([_segment(long_sentence, index=n) for n in range(6)])
    for passage in build_passages(document):
        assert len(passage.text) <= MAX_CHARACTERS or len(passage.segment_ids) == 1


def test_the_version_is_carried_so_a_correction_invalidates_the_index() -> None:
    """An answer citing a passage that no longer exists is worse than no answer."""
    segments = [_segment("අන්තර්ගතය.", index=0)]
    one = build_passages(_document(segments, version="v1"))[0]
    two = build_passages(_document(segments, version="v2"))[0]
    assert one.document_version != two.document_version
    assert one.passage_id != two.passage_id


def test_the_same_text_at_the_same_version_keeps_its_id() -> None:
    """Otherwise every rebuild reindexes the whole book."""
    segments = [_segment("අන්තර්ගතය.", index=0)]
    one = build_passages(_document(segments))[0]
    two = build_passages(_document(segments))[0]
    assert one.passage_id == two.passage_id


def test_line_breaks_from_the_page_do_not_survive_into_a_passage() -> None:
    document = _document([_segment("පළමු පේළිය\nදෙවන පේළිය", index=0)])
    (passage,) = build_passages(document)
    assert passage.text == "පළමු පේළිය දෙවන පේළිය"


def test_a_document_with_nothing_readable_produces_no_passages() -> None:
    assert build_passages(_document([])) == ()


def test_a_heading_alone_is_not_a_passage() -> None:
    """It would match every question about the section and answer none of them."""
    document = _document([_segment("1.1 ආරම්භය", index=0, role=BlockRole.HEADING, level=2)])
    assert build_passages(document) == ()


def test_passages_are_in_reading_order() -> None:
    document = _document([_segment(f"වාක්‍ය {n}.", index=n, page=n) for n in range(5)])
    passages: tuple[Passage, ...] = build_passages(document)
    assert [p.page_index for p in passages] == sorted(p.page_index for p in passages)
