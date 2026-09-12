"""What a block of a page *is*, and what follows from that.

A page is not prose. A table of contents, a figure caption, a heading, an
address and a running header are different kinds of thing, and flattening them
into one stream is what produces both mis-structured narration and incorrect
number reading. Measured on a real Grade 11 textbook, that flattening reads a
contents row "1 • 18" as "one bullet eighteen", a house number 65C as the
quantity sixty-five, and — worst — splices a figure caption into the middle of
the sentence it happens to sit beside, so a listener hears the caption interrupt
a sentence and has no way to see that it did.

This module holds the vocabulary. It does not classify anything: assigning a
role to a block is the job of an adapter, deterministic or otherwise, and the
roles have to exist before anything can produce or verify them.

Two consequences hang off a role, and they are why the vocabulary is worth
having rather than being a label nobody reads:

* **How its numbers are read.** A number cannot be read correctly without
  knowing what contains it. See :func:`number_style_for`.
* **Whether it is narrated at all.** See :func:`is_narrated`.
"""

from __future__ import annotations

from enum import StrEnum

from sinhala_tts.normalize import NumberStyle


class BlockRole(StrEnum):
    """What a block of text is, within its page."""

    PARAGRAPH = "paragraph"
    """Running prose. The default, and most of a book."""

    HEADING = "heading"
    """A title for what follows, carrying a level.

    Its number is a label: "1.1 කාර්මික විප්ලවය" is section one one, not
    section one point one.
    """

    CAPTION = "caption"
    """Text belonging to a figure, table or image rather than to the prose.

    Kept separate above all: read in place it interrupts a sentence, and a
    listener cannot see that the interruption happened.
    """

    LIST_ITEM = "list_item"

    CONTENTS_ROW = "contents_row"
    """A row of the පටුන: a title, and the page it starts on.

    Its numbers are a chapter and a page — references to navigate by, never
    quantities to state.
    """

    TABLE_CELL = "table_cell"

    RUNNING_HEAD = "running_head"
    """A header or footer repeated across pages, such as a chapter title.

    Useful on paper and unbearable in audio, where it arrives between every
    page of a chapter.
    """

    PAGE_NUMBER = "page_number"
    """The printed page number. Navigation, not content."""

    ADDRESS = "address"
    """A postal address. Its digits name a place; they do not count anything."""

    UNKNOWN = "unknown"
    """Not classified.

    Explicit rather than absent, and treated exactly as a paragraph, so that a
    page nothing could classify still reads as well as it does today. A role
    that is missing and a role that is genuinely undetermined are different
    facts, and only one of them is worth reviewing.
    """


#: How each role's digits are read. Roles absent from this map read as prose.
#:
#: Written as a mapping rather than branches so that adding a role is a decision
#: someone has to make in one visible place, instead of silently inheriting
#: prose because a match arm was forgotten.
_NUMBER_STYLES: dict[BlockRole, NumberStyle] = {
    BlockRole.HEADING: NumberStyle.IDENTIFIER,
    BlockRole.CAPTION: NumberStyle.IDENTIFIER,
    BlockRole.CONTENTS_ROW: NumberStyle.IDENTIFIER,
    BlockRole.ADDRESS: NumberStyle.IDENTIFIER,
    BlockRole.PAGE_NUMBER: NumberStyle.IDENTIFIER,
}


def number_style_for(role: BlockRole) -> NumberStyle:
    """How to read the digits inside a block with this role.

    Prose is the default because it is both the commonest case and the safest
    one to be wrong about: reading a section number as a quantity is odd, while
    reading a quantity digit by digit loses the amount.
    """
    return _NUMBER_STYLES.get(role, NumberStyle.PROSE)


#: Roles that are not read aloud. Their text is still kept, still displayed and
#: still indexed — this decides narration only.
_NOT_NARRATED = frozenset({BlockRole.RUNNING_HEAD, BlockRole.PAGE_NUMBER})


def is_narrated(role: BlockRole) -> bool:
    """Whether a block with this role belongs in the audio.

    A running head is a navigation aid on paper and an interruption in audio,
    where it arrives between every page of a chapter with nothing to skip it.

    This is deliberately not deletion. CLAUDE.md requires the printed page label
    to be retained, and a reader who asks "what page am I on" must be answerable
    — so the text stays and only the narration drops it.
    """
    return role not in _NOT_NARRATED
