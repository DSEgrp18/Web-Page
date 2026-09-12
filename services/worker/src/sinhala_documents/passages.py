"""Section-aware passages: the unit a question is answered from.

A segment is the unit of *speech* — one sentence, sized to what the model can
say in one breath. It is far too small to answer a question from: "ඒ අනුව" is a
complete segment and means nothing on its own. A passage is the unit of
*evidence*, and the two are deliberately different things over the same text.

What makes a passage section-aware, and why it matters
------------------------------------------------------
A passage never crosses a heading. Text under "1.1 කාර්මික විප්ලවයේ ආරම්භය" and
text under "1.2 කාර්මික විප්ලවයේ ප්‍රබෝධය" answer different questions, and a
passage spanning the boundary retrieves for both and supports neither.

That boundary only exists because structure exists. Before headings were
recovered, every page was one undifferentiated run and this module could not
have been written — which is the payoff for the structure work arriving first.

Each passage also carries the headings above it. A reader asking about the
industrial revolution should be told they are hearing section 1.1 of chapter 1,
not handed a paragraph with no idea where it sits, and a citation without a
section is a page number the reader has to go and search.

Captions travel with their section rather than being dropped. A figure caption
is often the only place a date or a name appears, and the fact that it reads
badly *in sequence* — which is why it is a separate block for narration — has no
bearing on whether it is evidence.

Running heads are excluded. They repeat on every page, so they match everything
and distinguish nothing.

On sizing
---------
CLAUDE.md asks for roughly 300-600 model tokens. Nothing here knows the
answering model's tokenizer, and Sinhala does not tokenize like English, so this
counts **characters** and says so rather than reporting a token number it cannot
measure. The default target is deliberately a starting point to be tuned by
evaluation, not a figure anybody has validated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .pipeline import ReadableDocument, ReadableSegment
from .structure import BlockRole

#: Target passage size in characters. A starting point for evaluation to move,
#: not a measured optimum. Sinhala is written compactly, so this is nearer the
#: upper end of CLAUDE.md's 300-600 token range than the character count
#: suggests to an English-reading eye.
TARGET_CHARACTERS = 900

#: Never emit a passage longer than this, even when a single segment is huge.
MAX_CHARACTERS = 1600

#: Roles that are evidence. Headings are excluded as passage *bodies* because
#: they are carried as the section path instead, where they label every passage
#: beneath them rather than forming one short passage of their own that matches
#: every question about the section and answers none of them.
_EVIDENCE = frozenset(
    {
        BlockRole.PARAGRAPH,
        BlockRole.CAPTION,
        BlockRole.LIST_ITEM,
        BlockRole.TABLE_CELL,
        BlockRole.CONTENTS_ROW,
        BlockRole.ADDRESS,
        BlockRole.UNKNOWN,
    }
)


@dataclass(frozen=True)
class Passage:
    """A retrievable piece of a document, with everything a citation needs."""

    passage_id: str
    document_version: str
    """Which version of the text this came from.

    A correction creates a new version and must invalidate the index built from
    the old one: CLAUDE.md requires it, and an answer citing a passage that no
    longer exists is worse than no answer.
    """

    text: str
    page_index: int
    page_label: str | None
    """The *printed* page number, when the book has one. What a reader is told,
    because it is what they would find in the physical book."""

    section_path: tuple[str, ...] = ()
    """The headings above this passage, outermost first."""

    segment_ids: tuple[str, ...] = ()
    """The segments this passage covers, so a citation can be *played* rather
    than only shown. This is what makes a citation reachable without sight."""

    roles: tuple[BlockRole, ...] = field(default=())

    @property
    def section(self) -> str:
        return " › ".join(self.section_path)


def _passage_id(document_version: str, text: str, page_index: int) -> str:
    """Identity derived from content and place, so it is stable across rebuilds.

    Including the document version means a corrected page produces new passage
    ids rather than silently changing what an old id refers to.
    """
    digest = hashlib.sha256(f"{document_version}|{page_index}|{text}".encode()).hexdigest()
    return f"p_{digest[:16]}"


def _section_path(stack: dict[int, str]) -> tuple[str, ...]:
    return tuple(stack[level] for level in sorted(stack))


def build_passages(
    document: ReadableDocument,
    *,
    target: int = TARGET_CHARACTERS,
    maximum: int = MAX_CHARACTERS,
) -> tuple[Passage, ...]:
    """Group a document's segments into passages that can answer a question.

    Segments are grouped in reading order until the target size is reached, and
    never across a heading or a page. Not across a page because a citation names
    one page: a passage spanning two can only cite the wrong one for half its
    content.
    """
    passages: list[Passage] = []
    stack: dict[int, str] = {}
    current: list[ReadableSegment] = []
    current_page: int | None = None
    current_path: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal current, current_page
        if not current:
            return
        # Whitespace normalised per segment: the line breaks are the page's, not
        # the text's, and a passage is read rather than looked at.
        text = " ".join(" ".join(s.display_text.split()) for s in current).strip()
        if text:
            first = current[0]
            passages.append(
                Passage(
                    passage_id=_passage_id(document.version, text, first.page_index),
                    document_version=document.version,
                    text=text,
                    page_index=first.page_index,
                    page_label=first.page_label,
                    section_path=current_path,
                    segment_ids=tuple(s.segment_id for s in current),
                    roles=tuple(dict.fromkeys(s.role for s in current)),
                )
            )
        current = []
        current_page = None

    for segment in document.segments:
        if segment.role is BlockRole.HEADING:
            # A heading closes whatever it follows and relabels what comes next.
            flush()
            level = segment.level or 1
            stack = {at: title for at, title in stack.items() if at < level}
            stack[level] = " ".join(segment.display_text.split())
            current_path = _section_path(stack)
            continue

        if segment.role not in _EVIDENCE:
            # Running heads and page numbers: they repeat on every page, so they
            # match every question and distinguish nothing.
            continue

        if current_page is not None and segment.page_index != current_page:
            flush()

        size = sum(len(s.display_text) for s in current)
        if current and size + len(segment.display_text) > maximum:
            flush()

        if current_page is None:
            current_page = segment.page_index
            current_path = _section_path(stack)
        current.append(segment)

        if sum(len(s.display_text) for s in current) >= target:
            flush()

    flush()
    return tuple(passages)
