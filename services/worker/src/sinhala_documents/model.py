"""What an extracted page is, before anyone decides what to do with it.

Two things are kept apart here, because conflating them is how a reader ends up
narrating nonsense confidently:

* **How the text was obtained** — :class:`ExtractionMethod`. Embedded Unicode,
  embedded legacy-font bytes, or optical recognition.
* **Whether it can be trusted** — :class:`QualityState`. Accepted, in need of
  human review, or known to be undecodable.

They are independent. Native extraction can produce garbage when the PDF uses a
pre-Unicode Sinhala font; OCR can produce clean text from a good scan. A single
"confidence" number would collapse the two and lose the only distinction that
tells the reader whether to speak.

Every span also keeps its box on the page. Highlighting, citations, and "read
from here" all need to point at something the reader can be shown, and once
geometry is discarded during assembly it cannot be recovered.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class ExtractionMethod(StrEnum):
    """How a piece of text was obtained from the document."""

    NATIVE = "native"
    """Embedded text with a usable Unicode mapping."""

    LEGACY = "legacy"
    """Embedded text in a pre-Unicode Sinhala font encoding.

    The characters that come out of the PDF are the font's own byte values
    reinterpreted as Latin, not Sinhala. They mean nothing until converted.
    """

    OCR = "ocr"
    """Recognised from an image. Not implemented yet."""

    NONE = "none"
    """Nothing was extracted."""


class QualityState(StrEnum):
    """Whether extracted text may be narrated and indexed."""

    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    UNDECODABLE = "undecodable"


#: Ordering used when a container takes the state of its worst part. A line of
#: mostly good text containing one undecodable span is not an accepted line.
_SEVERITY = {
    QualityState.ACCEPTED: 0,
    QualityState.NEEDS_REVIEW: 1,
    QualityState.UNDECODABLE: 2,
}


def worst(states: Iterable[QualityState]) -> QualityState:
    """The least trustworthy state among ``states``, or accepted if empty."""
    return max(states, key=lambda state: _SEVERITY[state], default=QualityState.ACCEPTED)


class PageKind(StrEnum):
    """What a page turned out to contain.

    Classified per page, never per document: CLAUDE.md requires it, and real
    books mix a typeset chapter with a scanned diagram page freely.
    """

    TEXT = "text"
    IMAGE = "image"
    """Images and no usable text. Needs OCR before it can be read."""

    MIXED = "mixed"
    """Both. The text is usable; the images are not described."""

    EMPTY = "empty"


@dataclass(frozen=True)
class BoundingBox:
    """A rectangle in PDF page space, y measured downwards from the top.

    Downwards because that is what pdfplumber reports and what a reader sees.
    PDF's own coordinate system has the origin at the bottom; converting once,
    here, is better than every caller remembering which convention it holds.
    """

    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @staticmethod
    def around(boxes: Iterable[BoundingBox]) -> BoundingBox | None:
        """The smallest box containing all of ``boxes``."""
        items = list(boxes)
        if not items:
            return None
        return BoundingBox(
            x0=min(box.x0 for box in items),
            top=min(box.top for box in items),
            x1=max(box.x1 for box in items),
            bottom=max(box.bottom for box in items),
        )


@dataclass(frozen=True)
class TextSpan:
    """A run of characters sharing a font and size.

    The span is the unit at which legacy fonts are identified, because a page
    can put a Unicode heading above a legacy body and applying one verdict to
    the whole page would either reject the heading or narrate the body as
    gibberish.
    """

    text: str
    font: str
    """Font name with the subset prefix removed, for identification."""

    raw_font: str
    """Exactly what the PDF recorded, kept for diagnosis and provenance."""

    size: float
    box: BoundingBox
    method: ExtractionMethod = ExtractionMethod.NATIVE
    quality: QualityState = QualityState.ACCEPTED
    notes: tuple[str, ...] = ()
    """Why this span is not accepted, in language a person can act on."""

    original_text: str = ""
    """What the PDF actually contained, when ``text`` was decoded from it.

    Empty when nothing was transformed. CLAUDE.md requires the original
    extraction to be preserved alongside corrected text, and a legacy
    conversion is the one place here where what is spoken is not what the file
    held. Without it a mistranslation cannot be diagnosed, because the evidence
    has been overwritten."""


@dataclass(frozen=True)
class TextLine:
    """One visual line, in reading order within its page."""

    spans: tuple[TextSpan, ...]
    box: BoundingBox

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def quality(self) -> QualityState:
        return worst(span.quality for span in self.spans)

    @property
    def methods(self) -> frozenset[ExtractionMethod]:
        return frozenset(span.method for span in self.spans)


@dataclass(frozen=True)
class PageExtraction:
    """Everything one page yielded, with the provenance to defend it."""

    page_index: int
    """Zero-based position in the file. Always known."""

    page_label: str | None
    """The page number as printed, when the PDF declares one.

    Books number front matter separately, so the twelfth page of the file is
    often printed "vi". Citations and "go to page" must use what the reader
    would see, and this is the only place it exists.
    """

    width: float
    height: float
    kind: PageKind
    lines: tuple[TextLine, ...] = ()
    image_count: int = 0
    notes: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """Every line, including any that must not be narrated.

        Use :attr:`readable_lines` for anything the reader will hear.
        """
        return "\n".join(line.text for line in self.lines)

    @property
    def readable_lines(self) -> tuple[TextLine, ...]:
        """Lines fit to narrate and index.

        Undecodable lines are withheld rather than dropped from the page: they
        stay in :attr:`lines` with their geometry, so the interface can say that
        part of this page could not be read instead of pretending it was blank.
        """
        return tuple(line for line in self.lines if line.quality is not QualityState.UNDECODABLE)

    @property
    def readable_text(self) -> str:
        return "\n".join(line.text for line in self.readable_lines)

    @property
    def quality(self) -> QualityState:
        """The state of the page as a whole, text and unread images together.

        A page of pictures and no text has no bad text on it, so judging it by
        its lines alone reports it as accepted — which would tell a reader the
        page is fine when in truth it has not been read at all.
        """
        state = worst(line.quality for line in self.lines)
        if self.kind is PageKind.IMAGE:
            return worst([state, QualityState.NEEDS_REVIEW])
        return state

    @property
    def methods(self) -> frozenset[ExtractionMethod]:
        return frozenset().union(*(line.methods for line in self.lines)) or frozenset(
            {ExtractionMethod.NONE}
        )


@dataclass(frozen=True)
class DocumentExtraction:
    """A whole file's pages plus what the extractor could not do."""

    pages: tuple[PageExtraction, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def pages_needing_ocr(self) -> tuple[PageExtraction, ...]:
        return tuple(page for page in self.pages if page.kind is PageKind.IMAGE)

    @property
    def pages_needing_review(self) -> tuple[PageExtraction, ...]:
        return tuple(page for page in self.pages if page.quality is not QualityState.ACCEPTED)
