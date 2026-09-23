"""Reading a page as a picture, with Tesseract, on this machine.

## Why a digital PDF needs this at all

The Grade 11 history textbook this reader was built against has no scanned
pages. It still has pages whose embedded text is not the text printed on them:

- **Page 121 (printed 111) holds two copies of itself**, set at 12 and 10.6
  points with different line breaks, and only one is visible. Extraction reads
  both. Where their lines land close together the characters interleave into
  gibberish, so the page's list of thirteen colonies came out with four names
  missing and its last paragraph withheld as undecodable.
- **The front matter and contents** are in legacy fonts the converter cannot
  decode, so 22 pages have lines withheld from narration.

A picture of the page has neither problem, because it is what a sighted reader
sees. Tesseract read page 121 with every line once, all thirteen names, and
about six wrong characters in 1,500.

## What recognition costs

Recognition invents where extraction does not. On that same page it wrote
පෙන්සිල්චේනියා for පෙන්සිල්වේනියා. So recognised text is always
``ExtractionMethod.OCR`` and ``QualityState.NEEDS_REVIEW``: narrated, and
announced as possibly misread. CLAUDE.md is explicit that OCR confidence is not
a calibrated probability of correctness, so the per-word confidence Tesseract
reports is kept out of that decision.

## Why Tesseract

It is free, Apache-2.0 licensed, and runs locally, so a reader's private
document never leaves the machine — unlike a vision model, which is external
processing of private material. Its Sinhala model is the ``sin`` traineddata.

**One page is not an evaluation.** CLAUDE.md asks for OCR to be benchmarked on
representative pages against ground truth. The evidence above is a reason to
build this, not a measurement of how well it works.
"""

from __future__ import annotations

import os
import subprocess
import unicodedata
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from .model import (
    BoundingBox,
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    PageKind,
    Progress,
    QualityState,
    TextLine,
    TextSpan,
)

#: Bump on any change to rendering, recognition settings, or how words become
#: lines. Part of the adapter version, and so of provenance and cache identity.
OCR_VERSION = "1"

#: The Tesseract executable. Overridable for a machine where it is not on PATH.
TESSERACT_ENV = "SINHALA_READER_TESSERACT"

#: Rendering resolution. 300 dpi is what page 121 was measured at. Sinhala needs
#: the headroom more than Latin script does: its distinguishing marks are small
#: loops and strokes above and below the letter, and they are the first thing
#: lost when a page is downsampled.
DEFAULT_DPI = 300

LANGUAGE = "sin"

#: Tesseract's fully automatic page segmentation, which finds columns, blocks
#: and lines itself.
PAGE_SEGMENTATION = 3

#: How long one page may take. A 300 dpi page takes seconds; a minute means
#: something is wrong with the page, not that it needs longer.
TIMEOUT_SECONDS = 120

_AL_LAKUNA = "\u0dca"
_ZWNJ = "\u200c"

NOTE = (
    "This page was read from its image by optical character recognition. Recognition "
    "can misread letters, and this page has not been checked by a person."
)


class OcrUnavailable(RuntimeError):
    """No recognised text could be obtained.

    Every reason means the same thing to the caller — keep the page as it was —
    so they are not distinguished: no engine installed, no Sinhala model, a
    timeout, an unreadable image.
    """


@dataclass(frozen=True)
class OcrWord:
    """One recognised word, in pixels of the rendered image."""

    text: str
    left: int
    top: int
    width: int
    height: int
    block: int
    paragraph: int
    line: int
    confidence: float
    """Tesseract's own score. Not a probability of being right; never used to
    decide whether text is narrated."""


def normalise(text: str) -> str:
    """Remove what Tesseract adds that the printed page does not have.

    Tesseract writes a zero-width non-joiner after every al-lakuna (්) — 42 of
    them on page 121. It changes nothing visible, but typed questions do not
    contain it, so retrieval would never match a word that has one.

    Only that: the zero-width *joiner* is part of Sinhala spelling — it builds
    the rakaransaya in ප්‍ර and the yansaya in ය — and CLAUDE.md requires joiners
    to be preserved.
    """
    text = text.replace(_AL_LAKUNA + _ZWNJ, _AL_LAKUNA)
    return unicodedata.normalize("NFC", text)


def parse_tsv(tsv: str) -> tuple[OcrWord, ...]:
    """Words from Tesseract's TSV output, in the order it read them.

    Rows of other levels (page, block, paragraph, line) carry geometry but no
    text; only level 5 is a word.
    """
    words: list[OcrWord] = []
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < 12 or cells[0] != "5":
            continue
        text = normalise(cells[11].strip())
        if not text:
            continue
        try:
            words.append(
                OcrWord(
                    text=text,
                    left=int(cells[6]),
                    top=int(cells[7]),
                    width=int(cells[8]),
                    height=int(cells[9]),
                    block=int(cells[2]),
                    paragraph=int(cells[3]),
                    line=int(cells[4]),
                    confidence=float(cells[10]),
                )
            )
        except ValueError:
            continue
    return tuple(words)


def _is_decoration(text: str) -> bool:
    """A word with no letter or digit in it, such as a bullet read as "&*"."""
    return not any(unicodedata.category(c)[0] in {"L", "N"} for c in text)


def lines_from_words(words: tuple[OcrWord, ...], *, dpi: int, version: str) -> tuple[TextLine, ...]:
    """Group words into lines, in reading order, with boxes in page points.

    Tesseract numbers lines within paragraphs within blocks, and emits them in
    the order it read the page, so that order is kept rather than re-sorted by
    position: re-sorting would undo its column detection.

    A line's leading decorations are dropped — the ❖ bullet on page 121 came out
    as "&*" and would be read aloud as punctuation. Symbols *inside* a line are
    kept, because a dash or bracket there is part of the text.
    """
    scale = 72.0 / dpi
    grouped: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        grouped.setdefault((word.block, word.paragraph, word.line), []).append(word)

    lines: list[TextLine] = []
    for members in grouped.values():
        while members and _is_decoration(members[0].text):
            members = members[1:]
        if not members:
            continue
        boxes = [
            BoundingBox(
                x0=word.left * scale,
                top=word.top * scale,
                x1=(word.left + word.width) * scale,
                bottom=(word.top + word.height) * scale,
            )
            for word in members
        ]
        box = BoundingBox.around(boxes)
        assert box is not None
        heights = sorted(word.height for word in members)
        span = TextSpan(
            text=" ".join(word.text for word in members),
            font="",
            raw_font=version,
            # The median word height. Not a font size — it includes ascenders
            # and descenders — but it is comparable between lines of one page,
            # which is what telling a heading from body text needs.
            size=round(heights[len(heights) // 2] * scale, 1),
            box=box,
            method=ExtractionMethod.OCR,
            quality=QualityState.NEEDS_REVIEW,
            notes=(NOTE,),
        )
        lines.append(TextLine(spans=(span,), box=box))
    return tuple(lines)


class OcrAdapter(ABC):
    """Recognise the words in a rendered page."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Engine, language model and settings. Part of provenance and cache identity."""

    @abstractmethod
    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        """Words in reading order.

        Raises:
            OcrUnavailable: if no answer could be obtained.
        """


class TesseractOcr(OcrAdapter):
    """Tesseract with its Sinhala model, run as a subprocess."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        timeout: int = TIMEOUT_SECONDS,
        run=subprocess.run,
    ) -> None:
        self._executable = executable or os.environ.get(TESSERACT_ENV, "").strip() or "tesseract"
        self._timeout = timeout
        self._run = run
        self._engine: str | None = None

    def _engine_version(self) -> str:
        """The installed engine's version, asked once.

        Recorded because a different Tesseract build is a different recogniser:
        the same page read by 5.3 and 5.5 is two extractions.
        """
        if self._engine is None:
            result = self._invoke(["--version"], None)
            first = result.stdout.decode("utf-8", "replace").strip().splitlines()
            self._engine = first[0].split()[-1] if first else "unknown"
        return self._engine

    @property
    def version(self) -> str:
        try:
            engine = self._engine_version()
        except OcrUnavailable:
            engine = "unavailable"
        return f"tesseract/{engine}/{LANGUAGE}/psm{PAGE_SEGMENTATION}/ocr-{OCR_VERSION}"

    def _invoke(self, arguments: list[str], stdin: bytes | None):
        try:
            result = self._run(
                [self._executable, *arguments],
                input=stdin,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as error:
            raise OcrUnavailable(
                f"Tesseract is not installed (looked for {self._executable!r})."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise OcrUnavailable(f"Tesseract took longer than {self._timeout}s.") from error
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
            raise OcrUnavailable(
                f"Tesseract failed: {detail[-1] if detail else f'exit {result.returncode}'}"
            )
        return result

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        # "stdin" and "stdout" are Tesseract's own names for the pipes, so no
        # image or text is ever written to disk.
        result = self._invoke(
            ["stdin", "stdout", "-l", LANGUAGE, "--psm", str(PAGE_SEGMENTATION), "tsv"],
            image_png,
        )
        return parse_tsv(result.stdout.decode("utf-8", "replace"))


def render_page(source: bytes | str | Path, page_index: int, *, dpi: int = DEFAULT_DPI) -> bytes:
    """One page of a PDF as PNG bytes, as a viewer would draw it."""
    import io

    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as error:
        raise OcrUnavailable(f"The PDF could not be opened for rendering: {error}") from error
    try:
        if not 0 <= page_index < len(document):
            raise OcrUnavailable(f"Page {page_index} is not in this document.")
        try:
            image = document[page_index].render(scale=dpi / 72).to_pil()
        except pdfium.PdfiumError as error:
            raise OcrUnavailable(f"Page {page_index} could not be rendered: {error}") from error
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        document.close()


def recognise_page(
    page: PageExtraction,
    image_png: bytes,
    adapter: OcrAdapter,
    *,
    dpi: int = DEFAULT_DPI,
) -> PageExtraction:
    """The same page, with its lines replaced by what recognition read.

    Everything else about the page is kept — its index, printed label, size and
    images — because it is still the same page. Its lines are replaced whole
    rather than merged: mixing recognised and extracted lines on one page would
    duplicate whatever both read, which is the problem this exists to solve.

    Raises:
        OcrUnavailable: if recognition failed. The caller keeps the page it had.
    """
    words = adapter.recognise(image_png)
    lines = lines_from_words(words, dpi=dpi, version=adapter.version)
    has_text = any(line.text.strip() for line in lines)
    if has_text:
        kind = PageKind.MIXED if page.image_count else PageKind.TEXT
    else:
        kind = PageKind.IMAGE if page.image_count else PageKind.EMPTY
    # The extractor's own page notes, rebuilt for the new lines, so that "this
    # page has images that are not described" survives. Its notes about withheld
    # legacy text do not, because that text is no longer what is read.
    from .pdf_extract import _page_notes

    notes = (NOTE, *_page_notes(kind, page.image_count, lines, columns=False))
    return replace(page, lines=lines, kind=kind, notes=notes)


class OcrMode(StrEnum):
    """Which pages are read from their image."""

    OFF = "off"
    """None. The text layer is all there is, and broken pages stay unread."""

    BROKEN = "broken"
    """Only pages whose text layer failed. Every other page keeps its exact
    embedded text, which recognition could only make worse."""

    ALL = "all"
    """Every page. Consistent, and slower; adds recognition errors to pages whose
    embedded text was already exact."""


#: A page repeating this many of its own lines is holding a hidden copy of
#: itself. Page 121 repeated five. One repeat is left alone: a refrain, a
#: repeated heading, or two table rows can legitimately match.
DUPLICATED_LINES = 2

#: Lines shorter than this are not counted as repeats. "1." and a page number
#: repeat on ordinary pages.
_REPEAT_MINIMUM = 20

#: A withheld line shorter than this, not counting spaces, is not worth reading a
#: whole page from its image for. On the real textbook, four of the pages with a
#: single withheld line were withholding "=", "a", "S" and "•": recognising those
#: pages would replace thirty exact lines with recognised ones to recover a
#: stray symbol. The other single withheld lines were real sentences.
_WITHHELD_MINIMUM = 5


def _withholds_text(line: TextLine) -> bool:
    """Whether the *withheld spans* of this line amount to text.

    The spans, not the line: on those pages the stray "=" sat inside a line of
    perfectly readable Sinhala, and counting the whole line counted that too.
    """
    withheld = "".join(span.text for span in line.spans if span.quality is QualityState.UNDECODABLE)
    return sum(not character.isspace() for character in withheld) >= _WITHHELD_MINIMUM


def text_layer_failed(page: PageExtraction) -> bool:
    """Whether this page's embedded text cannot be trusted to be what is printed.

    Three signals, each measured on the real textbook:

    - **Withheld lines.** Legacy text the converter cannot decode, or text that
      decodes to malformed Sinhala — ignoring stray fragments of a character or
      two. 17 of its 168 pages; with the two below, 19 are recognised.
    - **Repeated lines.** A hidden second copy of the page, read as well as the
      visible one. Pages 3, 5, 7, 8 and 121.
    - **No text at all on a page with images.** A scan.
    """
    if page.kind is PageKind.IMAGE:
        return True
    if any(_withholds_text(line) for line in page.lines):
        return True
    texts = [line.text.strip() for line in page.lines]
    counts = Counter(text for text in texts if len(text) >= _REPEAT_MINIMUM)
    return sum(count - 1 for count in counts.values()) >= DUPLICATED_LINES


def apply_ocr(
    extraction: DocumentExtraction,
    source: bytes | str | Path,
    adapter: OcrAdapter,
    mode: OcrMode,
    *,
    dpi: int = DEFAULT_DPI,
    render: Callable[..., bytes] = render_page,
    progress: Progress | None = None,
) -> DocumentExtraction:
    """The document with the chosen pages read from their images.

    A page recognition fails on keeps what extraction gave it, and the document
    says how many pages that happened to. Failing the whole book because
    Tesseract is missing would take away the pages that read perfectly well.
    """
    if mode is OcrMode.OFF:
        return extraction

    chosen = {
        page.page_index
        for page in extraction.pages
        if mode is not OcrMode.BROKEN or text_layer_failed(page)
    }
    pages: list[PageExtraction] = []
    failed: list[int] = []
    reason = ""
    done = 0
    for page in extraction.pages:
        if page.page_index not in chosen:
            pages.append(page)
            continue
        try:
            image = render(source, page.page_index, dpi=dpi)
            pages.append(recognise_page(page, image, adapter, dpi=dpi))
        except OcrUnavailable as error:
            pages.append(page)
            failed.append(page.page_index)
            reason = str(error)
        done += 1
        if progress is not None:
            progress("recognising", done, len(chosen))

    notes = list(extraction.notes)
    if failed:
        notes.append(
            f"{len(failed)} page(s) could not be read by optical character recognition "
            f"and keep their embedded text: {reason}"
        )
    return replace(extraction, pages=tuple(pages), notes=tuple(notes))
