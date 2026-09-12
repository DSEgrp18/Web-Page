"""The check that makes inferring structure with a model safe.

Written as the attacks it has to survive, because that is what it is for: this
is the only thing standing between a reader and a model that rewrote their
textbook.
"""

from __future__ import annotations

import pytest

from sinhala_documents.blocks import Block, verify
from sinhala_documents.structure import BlockRole

PAGE = (
    "1.1 කාර්මික විප්ලවයේ ආරම්භය\n"
    "18 වන සියවස අග භාගයේ දී බ්‍රිතාන්‍යයේ කාර්මික විප්ලවය ඇරඹිණි.\n"
    "රූපය 1.1 - 1764 වර්ෂයේ දී කපු යන්ත්‍රය"
)


def _good_blocks() -> list[Block]:
    """What a correct structuring of PAGE looks like: the caption pulled out."""
    return [
        Block(BlockRole.HEADING, "1.1 කාර්මික විප්ලවයේ ආරම්භය", level=2),
        Block(
            BlockRole.PARAGRAPH,
            "18 වන සියවස අග භාගයේ දී බ්‍රිතාන්‍යයේ කාර්මික විප්ලවය ඇරඹිණි.",
        ),
        Block(BlockRole.CAPTION, "රූපය 1.1 - 1764 වර්ෂයේ දී කපු යන්ත්‍රය"),
    ]


def test_a_faithful_structuring_verifies() -> None:
    assert verify(PAGE, _good_blocks())


def test_line_breaks_are_not_treated_as_edits() -> None:
    """Extracted text wraps where the page wrapped; joining it is not a change."""
    blocks = [Block(BlockRole.PARAGRAPH, PAGE.replace("\n", " "))]
    assert verify(PAGE, blocks)


def test_reordering_is_allowed_because_reading_order_is_the_point() -> None:
    """A two-column page extracts in the wrong order. Fixing it is a fix."""
    blocks = list(reversed(_good_blocks()))
    assert verify(PAGE, blocks)


def test_rephrasing_is_rejected() -> None:
    """The whole reason this function exists."""
    blocks = _good_blocks()
    blocks[1] = Block(BlockRole.PARAGRAPH, "කාර්මික විප්ලවය බ්‍රිතාන්‍යයේ ඇරඹිණි.")
    result = verify(PAGE, blocks)
    assert not result
    assert "not text from this page" in result.reason


def test_an_invented_heading_is_rejected() -> None:
    """A model adding the heading it thought was implied."""
    blocks = [*_good_blocks(), Block(BlockRole.HEADING, "සාරාංශය", level=2)]
    result = verify(PAGE, blocks)
    assert not result


def test_a_changed_digit_is_rejected() -> None:
    """1764 becoming 1784: invisible in the output, wrong in the book.

    A sighted proofreader catches this. A blind student cannot.
    """
    blocks = _good_blocks()
    blocks[2] = Block(BlockRole.CAPTION, blocks[2].text.replace("1764", "1784"))
    result = verify(PAGE, blocks)
    assert not result
    assert "8" in result.invented
    assert "6" in result.lost


def test_dropping_a_block_is_rejected() -> None:
    """Silently losing the caption is losing part of the book."""
    result = verify(PAGE, _good_blocks()[:2])
    assert not result
    assert result.lost


def test_duplicating_a_block_is_rejected() -> None:
    """A reader hearing the same sentence twice with nothing to explain it."""
    blocks = _good_blocks()
    result = verify(PAGE, [*blocks, blocks[1]])
    assert not result
    assert result.invented


def test_a_corrected_spelling_is_still_rejected() -> None:
    """Even an improvement is a word the document does not contain."""
    page = "බ්‍රිතාන්‍යයේ් කාර්මික විප්ලවය"
    blocks = [Block(BlockRole.PARAGRAPH, "බ්‍රිතාන්‍යයේ කාර්මික විප්ලවය")]
    assert not verify(page, blocks)


def test_an_empty_block_is_rejected() -> None:
    blocks = [*_good_blocks(), Block(BlockRole.PARAGRAPH, "   ")]
    result = verify(PAGE, blocks)
    assert not result
    assert "empty" in result.reason


def test_no_blocks_for_a_page_with_text_is_rejected() -> None:
    """Returning nothing must not be the easy way to pass."""
    result = verify(PAGE, [])
    assert not result
    assert "no blocks" in result.reason


def test_an_empty_page_expects_no_blocks() -> None:
    assert verify("   \n  ", [])
    assert not verify("  ", [Block(BlockRole.PARAGRAPH, "anything")])


def test_the_failure_names_what_was_added_and_what_was_lost() -> None:
    """Added and lost mean different things, so they are reported separately.

    Lost text is a reader not being told something. Invented text is a reader
    being told something the book does not say.
    """
    blocks = [Block(BlockRole.PARAGRAPH, PAGE.replace("\n", " ") + " සහ තවත්")]
    result = verify(PAGE, blocks)
    assert not result
    assert result.invented and not result.lost


def test_a_heading_must_carry_a_level() -> None:
    """A sidebar built from levelless headings is a flat list, not a hierarchy."""
    with pytest.raises(ValueError, match="level"):
        Block(BlockRole.HEADING, "1.1 කාර්මික විප්ලවය")


def test_only_a_heading_carries_a_level() -> None:
    with pytest.raises(ValueError, match="heading level"):
        Block(BlockRole.PARAGRAPH, "text", level=1)


def test_the_counts_are_not_truncated_with_the_report() -> None:
    """A page with many invented characters must not be described as having twelve."""
    page = "අකුරු"
    # Each block is genuinely page text, so the substring check passes and the
    # character accounting is what rejects it. Eleven copies of five characters
    # is fifty more than the page has.
    blocks = [Block(BlockRole.PARAGRAPH, "අකුරු")] * 11
    result = verify(page, blocks)
    assert not result
    assert "50 character(s) added" in result.reason
    assert len(result.invented) == 12


def test_a_block_is_located_back_in_the_page() -> None:
    """A block that has lost its offsets has lost its bounding boxes with it."""
    from sinhala_documents.blocks import locate

    spans = locate(PAGE, _good_blocks())
    assert all(span is not None for span in spans)
    for block, span in zip(_good_blocks(), spans, strict=True):
        assert PAGE[span[0] : span[1]].replace("\n", " ") == block.text.replace("\n", " ")


def test_locating_ignores_the_line_breaks_a_block_joined() -> None:
    """Joining wrapped lines is the point of a block, not a mismatch."""
    from sinhala_documents.blocks import locate

    page = "පළමු පේළිය\nදෙවන පේළිය"
    (span,) = locate(page, [Block(BlockRole.PARAGRAPH, "පළමු පේළිය දෙවන පේළිය")])
    assert span == (0, len(page))


def test_two_identical_blocks_get_two_places() -> None:
    """Otherwise a repeated heading points twice at its first occurrence."""
    from sinhala_documents.blocks import locate

    page = "ආරම්භය\nමැද\nආරම්භය"
    blocks = [Block(BlockRole.PARAGRAPH, "ආරම්භය"), Block(BlockRole.PARAGRAPH, "ආරම්භය")]
    first, second = locate(page, blocks)
    assert first != second
    assert first[0] < second[0]


def test_reordered_blocks_keep_their_own_places() -> None:
    """Reading order may differ from page order; the offsets follow the page."""
    from sinhala_documents.blocks import locate

    spans = locate(PAGE, list(reversed(_good_blocks())))
    assert [s[0] for s in spans] == sorted((s[0] for s in spans), reverse=True)


def test_a_block_that_cannot_be_placed_is_reported_not_raised() -> None:
    """A lost bounding box is a degraded page, not an unreadable one."""
    from sinhala_documents.blocks import locate

    (span,) = locate(PAGE, [Block(BlockRole.PARAGRAPH, "මෙය පිටුවේ නැත")])
    assert span is None


def test_a_joined_line_break_without_a_space_still_verifies() -> None:
    """Measured on the real book: the commonest rejection, and not an edit.

    The page wraps mid-sentence; a model joining the two lines without putting a
    space in has changed nothing a reader will ever encounter, because the
    pipeline re-slices the page's own characters once the block is located.
    """
    page = "නිපදවී ය.\nමගීින් ගෙන යාම"
    assert verify(page, [Block(BlockRole.PARAGRAPH, "නිපදවී ය.මගීින් ගෙන යාම")])


def test_a_substituted_character_is_still_rejected() -> None:
    """The other real rejection, which must keep failing.

    The page contains \x99, a control character left by a legacy font. The
    model returned ™ instead — a correction, and exactly what may not happen.
    """
    page = "\x99 මහා පරිමාණ ගොවිබිම්"
    result = verify(page, [Block(BlockRole.LIST_ITEM, "™ මහා පරිමාණ ගොවිබිම්")])
    assert not result
    assert "™" in result.invented
