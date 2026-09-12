"""The block-role vocabulary, and the two things that follow from a role."""

from __future__ import annotations

import pytest
from sinhala_tts.normalize import NumberStyle, to_speech_text

from sinhala_documents.structure import (
    BlockRole,
    is_narrated,
    number_style_for,
)


@pytest.mark.parametrize(
    ("role", "style"),
    [
        (BlockRole.PARAGRAPH, NumberStyle.PROSE),
        (BlockRole.LIST_ITEM, NumberStyle.PROSE),
        (BlockRole.TABLE_CELL, NumberStyle.PROSE),
        (BlockRole.UNKNOWN, NumberStyle.PROSE),
        (BlockRole.HEADING, NumberStyle.IDENTIFIER),
        (BlockRole.CAPTION, NumberStyle.IDENTIFIER),
        (BlockRole.CONTENTS_ROW, NumberStyle.IDENTIFIER),
        (BlockRole.ADDRESS, NumberStyle.IDENTIFIER),
        (BlockRole.PAGE_NUMBER, NumberStyle.IDENTIFIER),
    ],
)
def test_each_role_has_a_chosen_number_style(role: BlockRole, style: NumberStyle) -> None:
    assert number_style_for(role) is style


def test_every_role_is_covered_by_this_test() -> None:
    """A new role must not be able to inherit prose without anyone deciding."""
    tested = {
        BlockRole.PARAGRAPH,
        BlockRole.LIST_ITEM,
        BlockRole.TABLE_CELL,
        BlockRole.UNKNOWN,
        BlockRole.HEADING,
        BlockRole.CAPTION,
        BlockRole.CONTENTS_ROW,
        BlockRole.ADDRESS,
        BlockRole.PAGE_NUMBER,
        BlockRole.RUNNING_HEAD,
    }
    assert tested == set(BlockRole)


def test_an_unclassified_block_reads_exactly_as_it_does_today() -> None:
    """A page nothing could classify must not get worse than before."""
    assert number_style_for(BlockRole.UNKNOWN) is NumberStyle.PROSE
    assert is_narrated(BlockRole.UNKNOWN)


def test_running_heads_and_page_numbers_are_not_narrated() -> None:
    """A chapter title between every page, with nothing to skip it."""
    assert not is_narrated(BlockRole.RUNNING_HEAD)
    assert not is_narrated(BlockRole.PAGE_NUMBER)


def test_everything_else_is_narrated() -> None:
    silent = {BlockRole.RUNNING_HEAD, BlockRole.PAGE_NUMBER}
    for role in BlockRole:
        assert is_narrated(role) is (role not in silent), role


def test_the_real_defects_read_correctly_once_a_role_is_known() -> None:
    """The cases measured on the Grade 11 textbook, by the role they belong to."""
    heading = to_speech_text("1.1 කාර්මික විප්ලවය", numbers=number_style_for(BlockRole.HEADING))
    assert heading == "එක එක කාර්මික විප්ලවය"

    address = to_speech_text("අංක 65C", numbers=number_style_for(BlockRole.ADDRESS))
    assert address == "අංක හය පහ C"

    # A year in prose is still a quantity, and must not be caught by the above.
    prose = to_speech_text("හිට්ලර් 1933 දී බලයට පත් විය", numbers=number_style_for(BlockRole.PARAGRAPH))
    assert "එක්දහස් නවසිය තිස් තුන" in prose
