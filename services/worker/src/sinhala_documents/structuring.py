"""Choosing a page's structure, and surviving the chooser being wrong.

:mod:`.blocks` decides whether a structuring may be trusted. This decides what
to do about it, and the answer is the same in every failing case: use the
deterministic structure and record why.

The distinction that matters here is between a provider that **did not answer**
and a provider that **answered wrongly**. They look similar from the call site
and mean opposite things:

* Unavailable, rate-limited, timed out, not configured — the deterministic path
  is the documented default. Nothing is wrong with the document, so the page is
  accepted as it would have been with no provider at all.
* Answered, and the answer did not verify — something produced text that is not
  in this book. The page still falls back, but a human should see it, so it is
  marked for review rather than quietly accepted.

Collapsing those two into "it didn't work" would hide the only signal that a
model is misbehaving behind the ordinary noise of a network.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .blocks import Block, verify
from .model import QualityState
from .structure import BlockRole

log = logging.getLogger(__name__)


class StructureUnavailable(Exception):
    """The provider could not be reached or could not answer.

    Distinct from returning something wrong, which is not an exception: a wrong
    answer is a result that fails verification, and it is a result somebody
    should look at.
    """


class StructureAdapter(ABC):
    """``blocks_for(page_text) -> blocks``, however they are arrived at."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider, model and prompt version, for provenance and cache keys.

        CLAUDE.md requires structure to be provenance-bearing like any other
        extraction stage. A page structured by a different prompt is a different
        structuring, and audio generated from it must not be served from a cache
        entry made under the old one.
        """

    @abstractmethod
    def blocks_for(self, page_text: str) -> tuple[Block, ...]:
        """Structure this page.

        Raises:
            StructureUnavailable: if no answer could be obtained.
        """


class DeterministicStructure(StructureAdapter):
    """The structure we can derive with no provider at all: none.

    One block holding the page, its role explicitly :attr:`BlockRole.UNKNOWN`
    rather than paragraph. The distinction is not pedantry — unknown reads
    exactly as prose, so nothing is worse than it is today, while a page nobody
    has classified stays distinguishable from a page classified as prose. Only
    the first is worth revisiting when a provider becomes available.

    This is the path that must stay shippable, which CLAUDE.md requires: it is
    what runs when the provider is unavailable, unaffordable, or wrong.
    """

    @property
    def version(self) -> str:
        return "deterministic-1"

    def blocks_for(self, page_text: str) -> tuple[Block, ...]:
        if not page_text.strip():
            return ()
        return (Block(BlockRole.UNKNOWN, page_text),)


@dataclass(frozen=True)
class StructuredPage:
    """A page's blocks, and how much they can be trusted."""

    blocks: tuple[Block, ...]
    version: str
    """The adapter version that produced these blocks. Provenance, and part of
    cache identity."""
    quality: QualityState = QualityState.ACCEPTED
    note: str = ""
    """Why this is not the structure that was asked for, if it is not. Empty
    otherwise. Never contains document text: a note is logged and displayed, and
    CLAUDE.md forbids logging private passages."""


def structure_page(
    page_text: str,
    adapter: StructureAdapter,
    *,
    fallback: StructureAdapter | None = None,
) -> StructuredPage:
    """Structure a page, falling back to deterministic structure if anything is wrong.

    Never raises for a provider's failure. A book must remain readable when a
    structure provider is down, out of quota, or returning nonsense, and a
    reader who wanted to listen to chapter four does not care which.
    """
    fallback = fallback or DeterministicStructure()

    if adapter is fallback or isinstance(adapter, DeterministicStructure):
        return StructuredPage(adapter.blocks_for(page_text), adapter.version)

    try:
        blocks = adapter.blocks_for(page_text)
    except StructureUnavailable as unavailable:
        # The documented default path, not a defect. Accepted as it would have
        # been with no provider configured.
        log.info("structure provider unavailable, using deterministic structure: %s", unavailable)
        return StructuredPage(
            fallback.blocks_for(page_text),
            fallback.version,
            note="The structure service was unavailable, so this page is read as plain text.",
        )
    except Exception:
        # An adapter raising something else is a bug in the adapter. It must
        # still not take a book down, and unlike unavailability it is worth a
        # stack trace.
        log.exception("structure provider failed, using deterministic structure")
        return StructuredPage(
            fallback.blocks_for(page_text),
            fallback.version,
            quality=QualityState.NEEDS_REVIEW,
            note="The structure service failed, so this page is read as plain text.",
        )

    checked = verify(page_text, blocks)
    if checked:
        return StructuredPage(tuple(blocks), adapter.version)

    # Answered, and the answer was not this book. Falls back like the rest, and
    # is flagged, because this is the signal that a model is misbehaving and it
    # must not be lost in the ordinary noise of a network.
    log.warning("structure verification failed (%s): %s", adapter.version, checked.reason)
    return StructuredPage(
        fallback.blocks_for(page_text),
        fallback.version,
        quality=QualityState.NEEDS_REVIEW,
        note="The structure of this page could not be confirmed, so it is read as plain text.",
    )
