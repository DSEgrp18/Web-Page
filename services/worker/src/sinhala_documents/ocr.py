"""Reading a page as a picture, for the pages we cannot read as text.

CLAUDE.md's step 5 is "scanned PDFs with Sinhala OCR". The real Grade 11
textbook has **no scanned pages at all** — 86 mixed, 82 text, zero image-only —
so that is not what OCR earns its place doing here. What it earns its place
doing is the 22 pages marked ``undecodable``: pages whose text is present,
embedded, and in a pre-Unicode font that our mapping cannot convert. The
characters come out as Latin nonsense, and the page is silently unreadable while
looking, to the extractor, like text.

Those 22 pages include the front matter and the table of contents, which is
disproportionately the part a reader needs in order to navigate.

So OCR here is a **second opinion on a page we already have**, not a way to read
something that was never text. That difference matters for how it is used:

* It runs only where the text path failed. It is never a substitute for
  extraction that worked, because recognition invents and extraction does not.
* Its output is ``ExtractionMethod.OCR`` and ``QualityState.NEEDS_REVIEW``,
  always. CLAUDE.md is explicit that OCR confidence is not a calibrated
  probability of correctness, and a page recovered this way has not been checked
  by anybody.
* It has no verification available to it. The structure work could check a
  model's output against text we already had; here there is nothing to check
  against, which is exactly why the result is marked for review rather than
  accepted.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from pathlib import Path

#: Rendering resolution. 150 dpi puts a 12pt glyph at about 25 pixels tall,
#: which is comfortably above what recognisers need, and keeps a page around a
#: megabyte rather than four. Sinhala needs the headroom more than Latin does:
#: its distinguishing marks are small loops and strokes above and below the
#: base, and they are the first thing to disappear when a page is downsampled.
DEFAULT_DPI = 150

#: A guard, not a policy. A page that renders larger than this is not sent
#: anywhere, because something has gone wrong with it rather than because the
#: limit is meaningful.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class OcrUnavailable(Exception):
    """No recognised text could be obtained.

    Like :class:`~.structuring.StructureUnavailable`, every reason collapses
    into one: not configured, no network, a rate limit, an unreadable reply. The
    caller's response to all of them is the same, which is to leave the page
    flagged as it already was.
    """


def render_page(source: str | Path | bytes, page_index: int, *, dpi: int = DEFAULT_DPI) -> bytes:
    """One page of a PDF as PNG bytes.

    Deliberately separate from any recogniser. Rendering is the expensive,
    dependency-heavy half and is the same whichever recogniser runs, so it is
    worth being able to test, cache and inspect on its own — and worth being
    able to look at the picture a recogniser got when its answer is wrong.
    """
    import pdfplumber

    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(handle) as pdf:
        if page_index >= len(pdf.pages):
            raise OcrUnavailable(f"page {page_index} is not in this document")
        image = pdf.pages[page_index].to_image(resolution=dpi)
        buffer = io.BytesIO()
        image.original.save(buffer, format="PNG")

    data = buffer.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise OcrUnavailable(f"rendered page is {len(data)} bytes, over the limit")
    return data


class OcrAdapter(ABC):
    """``text_for(png) -> text``, however it is arrived at."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Engine, model and prompt version.

        Part of provenance and of cache identity: CLAUDE.md requires caching by
        content *plus* extraction engine and settings version, so a page read by
        a different recogniser is a different extraction.
        """

    @abstractmethod
    def text_for(self, image_png: bytes) -> str:
        """Recognise the Sinhala text in a rendered page.

        Raises:
            OcrUnavailable: if no answer could be obtained.
        """


class NoOcr(OcrAdapter):
    """The default: recognise nothing, and say so.

    Present so that "no OCR configured" is a value rather than a ``None`` every
    caller has to remember to check, and so the deterministic path stays the one
    that runs unless somebody chooses otherwise.
    """

    @property
    def version(self) -> str:
        return "no-ocr"

    def text_for(self, image_png: bytes) -> str:
        raise OcrUnavailable("no OCR engine is configured")
