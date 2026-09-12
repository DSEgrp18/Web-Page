"""Blocks of a page, and the check that makes inferring them safe.

CLAUDE.md permits a model to infer **structure** over text already extracted —
block roles, reading order, boundaries — and forbids it supplying the words. The
permission exists only because the second part is checkable, and this module is
where it is checked.

The verification is not a sanity check to be relaxed later. It is the entire
reason an external model is allowed near a reader's document at all, so it is
written to reject rather than to repair: a page that does not verify falls back
to deterministic structure and is marked for review, and nothing tries to work
out which half of a mismatched page was trustworthy.

Why blocks carry text rather than offsets
-----------------------------------------
Offsets into the page would make invention impossible by construction, since the
model would never supply a character. They are also the thing language models
are worst at: an off-by-one in an index is invisible in the output and silently
shifts a boundary into the middle of a word.

So blocks carry text, and :func:`verify` establishes the same guarantee after
the fact. It is stricter than it looks:

* Every block's text must appear in the page, so nothing can be invented or
  rephrased, and no block can be a scramble of words that are individually
  present.
* The characters of all blocks together must be exactly the characters of the
  page, counted, so nothing can be dropped, doubled, or quietly corrected.

Reordering is deliberately allowed. Recovering reading order is one of the
things structure inference is *for* — a two-column page is extracted in the
wrong order and putting it right is a fix, not a corruption.

What this cannot catch
----------------------
A model that swaps two identical words, or reorders blocks wrongly, produces
text this accepts. Character accounting proves nothing was invented or lost; it
does not prove the order is right. That is a real limit and the reason roles
carry provenance and pages carry a review state.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .structure import BlockRole

_WHITESPACE = re.compile(r"\s+")


def _flatten(text: str) -> str:
    """Collapse whitespace, so layout differences are not treated as edits.

    Extracted PDF text is full of line breaks the model will not reproduce, and
    a block that joined two wrapped lines has not changed the document.
    """
    return _WHITESPACE.sub(" ", text).strip()


def _characters(text: str) -> Counter[str]:
    """The characters that must be conserved, ignoring whitespace entirely."""
    return Counter(_flatten(text).replace(" ", ""))


@dataclass(frozen=True)
class Block:
    """One structural piece of a page."""

    role: BlockRole
    text: str
    level: int | None = None
    """Heading depth, 1 being the outermost. ``None`` for everything else."""

    def __post_init__(self) -> None:
        if self.level is not None and self.role is not BlockRole.HEADING:
            raise ValueError(f"{self.role} cannot carry a heading level")
        if self.role is BlockRole.HEADING and self.level is None:
            # A heading without a level cannot be placed in a contents tree, and
            # a sidebar built from levelless headings is a flat list wearing a
            # hierarchy's name.
            raise ValueError("a heading must carry a level")


@dataclass(frozen=True)
class Verification:
    """Whether a set of blocks may be trusted as this page's structure."""

    ok: bool
    reason: str = ""
    invented: tuple[str, ...] = field(default=())
    """Characters present in the blocks and not in the page."""
    lost: tuple[str, ...] = field(default=())
    """Characters present in the page and not in the blocks."""

    def __bool__(self) -> bool:
        return self.ok


#: How many differing characters to name before giving up on a useful message.
_MAX_REPORTED = 12


def verify(page_text: str, blocks: tuple[Block, ...] | list[Block]) -> Verification:
    """Whether ``blocks`` are a faithful structuring of ``page_text``.

    Returns rather than raises: a failure is an expected outcome with a defined
    response — fall back and mark for review — not an exceptional one.
    """
    if not _flatten(page_text):
        return (
            Verification(True)
            if not blocks
            else Verification(False, "blocks were produced for a page with no text")
        )
    if not blocks:
        return Verification(False, "no blocks were produced for a page that has text")

    page = _flatten(page_text)

    # Computed up front and attached to every failure. Which characters moved is
    # what a reviewer needs in order to see what happened, and it is no use only
    # on the branch that happens to notice first.
    from_page = _characters(page_text)
    from_blocks: Counter[str] = Counter()
    for block in blocks:
        from_blocks += _characters(block.text)
    all_invented = sorted((from_blocks - from_page).elements())
    all_lost = sorted((from_page - from_blocks).elements())
    # Truncated for the report only. The counts in the message come from the
    # full lists, or a page with fifty invented characters would be described
    # as having twelve.
    invented = tuple(all_invented[:_MAX_REPORTED])
    lost = tuple(all_lost[:_MAX_REPORTED])

    def failure(reason: str) -> Verification:
        return Verification(False, reason, invented=invented, lost=lost)

    for block in blocks:
        flattened = _flatten(block.text)
        if not flattened:
            return failure(f"a {block.role} block is empty")
        if flattened not in page:
            # The most important branch in this module. Anything the model wrote
            # itself lands here: a rephrasing, a completed sentence, a corrected
            # spelling, a heading it thought was implied.
            return failure(f"a {block.role} block is not text from this page: {flattened[:60]!r}")

    if from_blocks == from_page:
        return Verification(True)

    return failure(
        # Named separately because they mean different things: lost text is a
        # reader not being told something, invented text is a reader being told
        # something the book does not say. The second is far worse.
        f"the blocks do not account for the page exactly: "
        f"{len(all_invented)} character(s) added, {len(all_lost)} dropped"
    )
