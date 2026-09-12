"""Turn a PDF into the units a reader actually plays.

Extraction produces pages of lines; the speech front end produces segments a
model can pronounce. Nothing until now joined them, and the join is where the
decisions a reader feels get made:

* **Only text cleared for narration is segmented.** Undecodable lines are
  dropped here, not filtered downstream, so nothing that could not be read is
  ever handed to the synthesiser.
* **Segments never cross a page.** A citation has to name one page, and
  "read from here" has to land somewhere a reader can be shown. A sentence that
  runs across a page break is split at the break, which is a real limitation and
  is recorded as one.
* **Every segment keeps the boxes of the lines it covers.** That is what
  sentence highlighting draws, and it cannot be recovered later.
* **Identity is content-derived.** A segment keeps its id when other text in the
  document changes and gets a new one when its own text changes, which is what
  should invalidate its audio.

The document version combines the source bytes with the versions of everything
that transforms them. A change to the legacy converter or the number words
changes what the reader hears, so audio generated under the old ones has to be
invalidated — CLAUDE.md requires those versions in cache identity, and this is
where they enter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from sinhala_tts.normalize import MODEL_INPUT_CHAR_LIMIT, NORMALIZER_VERSION
from sinhala_tts.segmentation import Segment, segment_text

from .blocks import locate
from .legacy_fm_abhaya import CONVERTER_VERSION
from .model import (
    BoundingBox,
    DocumentExtraction,
    PageExtraction,
    PageKind,
    QualityState,
    worst,
)
from .pdf_extract import extract_document
from .structure import BlockRole, is_narrated, number_style_for
from .structuring import DeterministicStructure, StructureAdapter, structure_page

#: Bumped when this module changes how pages become segments.
PIPELINE_VERSION = "1"


@dataclass(frozen=True)
class ReadableSegment:
    """One thing the reader can play, highlight, resume at, or cite."""

    segment_id: str
    index: int
    """Position in the document, across all pages. What resume stores."""

    page_index: int
    page_label: str | None
    display_text: str
    """A slice of the page's readable text — what a reader sees."""

    spoken_text: str
    """Normalised Sinhala: numbers written out, whitespace regular. Reviewable."""

    model_text: str
    """Romanised ASCII the model is given. Meaningful to nothing else."""

    boxes: tuple[BoundingBox, ...]
    """The lines this segment covers, for highlighting."""

    role: BlockRole = BlockRole.UNKNOWN
    """What kind of thing this segment is part of.

    Decides how its numbers were read, and lets a reader be told that what they
    are hearing is a caption rather than the next sentence of the paragraph.
    """

    level: int | None = None
    """Heading depth, for a segment inside a heading. ``None`` otherwise."""

    @property
    def box(self) -> BoundingBox | None:
        """One rectangle around the whole segment."""
        return BoundingBox.around(self.boxes)


@dataclass(frozen=True)
class ReadablePage:
    """A page, with whatever of it can be spoken."""

    page_index: int
    page_label: str | None
    kind: PageKind
    quality: QualityState
    segments: tuple[ReadableSegment, ...]
    notes: tuple[str, ...]

    @property
    def has_audio(self) -> bool:
        return bool(self.segments)


@dataclass(frozen=True)
class ReadableDocument:
    """A document prepared for reading."""

    version: str
    """Identity of this text, for cache keys and resume.

    Derived from the source bytes and from every version that transforms them,
    so a change to the converter or the number words produces a new version and
    invalidates the audio generated under the old ones.
    """

    pages: tuple[ReadablePage, ...]
    notes: tuple[str, ...]

    @property
    def segments(self) -> tuple[ReadableSegment, ...]:
        return tuple(segment for page in self.pages for segment in page.segments)

    def segment(self, segment_id: str) -> ReadableSegment | None:
        return next((s for s in self.segments if s.segment_id == segment_id), None)

    def page(self, page_index: int) -> ReadablePage | None:
        return next((p for p in self.pages if p.page_index == page_index), None)


def _line_spans(page: PageExtraction) -> list[tuple[int, int, BoundingBox]]:
    """Where each readable line sits in the page's readable text.

    ``readable_text`` joins the lines with newlines, so the offsets segmentation
    reports can be mapped back to the lines — and therefore to the boxes — they
    came from.
    """
    spans: list[tuple[int, int, BoundingBox]] = []
    position = 0
    for line in page.readable_lines:
        length = len(line.text)
        spans.append((position, position + length, line.box))
        position += length + 1  # the joining newline
    return spans


def _boxes_for(
    segment: Segment, spans: list[tuple[int, int, BoundingBox]]
) -> tuple[BoundingBox, ...]:
    """Boxes of every line the segment overlaps."""
    return tuple(
        box
        for start, end, box in spans
        if start < segment.end_offset and end > segment.start_offset
    )


def _document_version(source_digest: str) -> str:
    """Identity of the text, not just of the file.

    The same PDF read with a different converter, or different number words, is
    a different document as far as generated audio is concerned.
    """
    parts = "|".join(
        [
            source_digest,
            f"pipeline={PIPELINE_VERSION}",
            f"converter={CONVERTER_VERSION}",
            f"normalizer={NORMALIZER_VERSION}",
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


def _digest(source: bytes | str | Path) -> str:
    if isinstance(source, bytes):
        return hashlib.sha256(source).hexdigest()
    digest = hashlib.sha256()
    with Path(source).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_pages(
    extraction: DocumentExtraction,
    *,
    limit: int = MODEL_INPUT_CHAR_LIMIT,
    structure: StructureAdapter | None = None,
) -> tuple[ReadablePage, ...]:
    """Segment each page's readable text, keeping geometry and page identity.

    Segmentation runs **per block** rather than per page, which is what lets a
    caption stop being read out in the middle of the sentence it sits beside,
    and what lets a heading's "1.1" be read as a section number instead of a
    decimal.

    The one thing worth being precise about: a block supplies its *role*, and
    never its text. Having located the block, the text segmented is this page's
    own slice — ``page.readable_text[begin:end]`` — so what a reader hears is
    always the characters we extracted, even if the structure came from a model.
    Verification already guarantees the two are the same; this makes it true by
    construction rather than by trust.
    """
    structure = structure or DeterministicStructure()
    pages: list[ReadablePage] = []
    index = 0
    for page in extraction.pages:
        spans = _line_spans(page)
        structured = structure_page(page.readable_text, structure)
        places = locate(page.readable_text, structured.blocks)

        if any(place is None for place in places):
            # A block nobody can place would take its text out of the document
            # entirely. Structure is an improvement; losing a paragraph is not a
            # trade worth making, so the whole page reverts to one block.
            structured = structure_page(page.readable_text, DeterministicStructure())
            places = locate(page.readable_text, structured.blocks)

        segments: list[ReadableSegment] = []
        notes = list(page.notes)
        if structured.note:
            notes.append(structured.note)

        for block, place in zip(structured.blocks, places, strict=True):
            if place is None or not is_narrated(block.role):
                # Still extracted, still displayed, still indexed. A running
                # head is a navigation aid on paper and an interruption in
                # audio, arriving between every page of a chapter.
                continue
            begin, _ = place
            body = page.readable_text[place[0] : place[1]]
            for segment in segment_text(body, limit=limit, numbers=number_style_for(block.role)):
                if not segment.is_speakable:
                    # Kept out of the reader entirely rather than played as
                    # silence.
                    continue
                # Offsets are within the block; the boxes are indexed by the
                # page, so they are shifted back before the lookup.
                placed = replace(
                    segment,
                    start_offset=segment.start_offset + begin,
                    end_offset=segment.end_offset + begin,
                )
                segments.append(
                    ReadableSegment(
                        segment_id=f"{page.page_index:04d}-{segment.segment_id}",
                        index=index,
                        page_index=page.page_index,
                        page_label=page.page_label,
                        display_text=segment.display_text,
                        spoken_text=segment.spoken_text,
                        model_text=segment.model_text,
                        boxes=_boxes_for(placed, spans),
                        role=block.role,
                        level=block.level,
                    )
                )
                index += 1

        pages.append(
            ReadablePage(
                page_index=page.page_index,
                page_label=page.page_label,
                kind=page.kind,
                quality=worst([page.quality, structured.quality]),
                segments=tuple(segments),
                notes=tuple(notes),
            )
        )
    return tuple(pages)


def prepare_document(
    source: bytes | str | Path,
    *,
    page_indexes: Iterable[int] | None = None,
    limit: int = MODEL_INPUT_CHAR_LIMIT,
    password: str = "",
    structure: StructureAdapter | None = None,
) -> ReadableDocument:
    """Extract, decode, and segment a PDF into playable units.

    ``page_indexes`` selects pages, so the section a reader asked for can be
    prepared before the rest of the book. The document version does not depend
    on which pages were chosen: it identifies the text, so a segment prepared
    alone and the same segment prepared with the whole book share a cache entry
    rather than generating the audio twice.
    """
    extraction = extract_document(source, page_indexes=page_indexes, password=password)
    version = _document_version(_digest(source))
    pages = prepare_pages(extraction, limit=limit, structure=structure)

    notes = list(extraction.notes)
    unreadable = [page.page_index for page in pages if not page.has_audio]
    if unreadable:
        notes.append(
            f"{len(unreadable)} of {len(pages)} page(s) have nothing that can be read aloud."
        )
    return ReadableDocument(version=version, pages=pages, notes=tuple(notes))
