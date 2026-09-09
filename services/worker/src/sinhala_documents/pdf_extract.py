"""Read a digital PDF into pages the rest of the reader can trust.

This is the "native" path: PDFs that carry real text, as opposed to scans.
CLAUDE.md asks for pages to be classified independently, for extraction method
to stay separate from quality, and for geometry and provenance to survive
assembly. All three are here.

What this deliberately does not do:

* **Convert legacy fonts.** They are identified and withheld. The mapping table
  is vendored but the converter is not written, and guessing would produce
  fluent Sinhala that says something the author did not write.
* **Recognise images.** Image-only pages are classified and reported so the
  interface can say what is missing.
* **Reorder columns.** Ambiguous reading order is flagged, not repaired.
* **Strip headers and footers.** Repeated-line removal needs the whole document
  and its own tests, including a story refrain that must survive.

Each of those is a later increment. Announcing the gap is the requirement; a
page that quietly returns nothing, or nonsense, is the failure mode this file
exists to avoid.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError

from .fonts import identify_legacy_font, looks_like_legacy_text
from .layout import suspects_multiple_columns
from .model import (
    BoundingBox,
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    PageKind,
    QualityState,
    TextLine,
    TextSpan,
)
from .page_labels import page_labels
from .validation import MAX_PAGES, DocumentRejected, check_pdf_bytes, check_pdf_file

#: Font size is rounded before it is used to break spans, so a renderer's
#: 11.999999 and 12.0 do not split a word in half.
_SIZE_PRECISION = 1

#: A horizontal gap wider than this fraction of the font size is read as a word
#: break. PDFs are under no obligation to contain space characters — many set
#: each word with a positioning operator instead — so a reconstruction that
#: trusts only real spaces runs whole sentences together. Expressed as a ratio
#: rather than the flat 3 points pdfplumber defaults to, because a footnote in
#: 7pt type and a heading in 24pt do not share a word gap.
_WORD_GAP_RATIO = 0.25

_LEGACY_CONVERTIBLE_NOTE = (
    "Text is in the legacy Sinhala font {name}. A conversion table exists for this family "
    "but the converter is not implemented, so the text cannot be read yet."
)

_LEGACY_UNSUPPORTED_NOTE = (
    "Text is in the legacy Sinhala font {name}, for which there is no validated conversion "
    "table. It needs optical recognition or manual review."
)

_SUSPECT_ENCODING_NOTE = (
    "The extracted characters do not look like Sinhala or ordinary English, which can mean "
    "an unrecognised legacy font. It needs checking."
)


def _box(item: dict) -> BoundingBox:
    return BoundingBox(
        x0=float(item["x0"]),
        top=float(item["top"]),
        x1=float(item["x1"]),
        bottom=float(item["bottom"]),
    )


def _classify_span(
    text: str, raw_font: str
) -> tuple[ExtractionMethod, QualityState, tuple[str, ...]]:
    """Decide how a run of text was encoded and whether it can be narrated."""
    legacy = identify_legacy_font(raw_font)
    if legacy is not None:
        template = _LEGACY_CONVERTIBLE_NOTE if legacy.convertible else _LEGACY_UNSUPPORTED_NOTE
        note = template.format(name=legacy.raw_name)
        return ExtractionMethod.LEGACY, QualityState.UNDECODABLE, (note,)

    if looks_like_legacy_text(text):
        # The font name did not give it away. This is a weak, uncalibrated
        # signal, so it asks for review rather than withholding the text: a
        # false positive here would silently hide a page that reads perfectly.
        return ExtractionMethod.NATIVE, QualityState.NEEDS_REVIEW, (_SUSPECT_ENCODING_NOTE,)

    return ExtractionMethod.NATIVE, QualityState.ACCEPTED, ()


def _span_key(char: dict) -> tuple[str, float]:
    size = round(float(char.get("size") or 0.0), _SIZE_PRECISION)
    return str(char.get("fontname") or ""), size


def _with_word_gaps(chars: Sequence[dict]) -> list[dict]:
    """Insert the spaces the PDF only implied by leaving a gap.

    Word breaks in a PDF are often geometry rather than characters, and
    pdfplumber's own word extractor discards the blank characters that *are*
    present. Reconstructing text from either alone produces one long run with
    no word boundaries — which segmentation would then treat as a single
    unsplittable token and the model would narrate as gibberish.

    The synthetic space carries the previous character's font and size so it
    joins that span rather than starting a new one.
    """
    out: list[dict] = []
    for char in chars:
        if out:
            previous = out[-1]
            gap = float(char["x0"]) - float(previous["x1"])
            size = float(previous.get("size") or 0.0) or float(char.get("size") or 0.0)
            wide = gap > max(size * _WORD_GAP_RATIO, 0.5)
            if wide and not previous["text"].isspace() and not char["text"].isspace():
                out.append(
                    {
                        **previous,
                        "text": " ",
                        "x0": previous["x1"],
                        "x1": char["x0"],
                    }
                )
        out.append(char)
    return out


def _spans(chars: Sequence[dict]) -> tuple[TextSpan, ...]:
    """Group a line's characters into runs sharing a font and size.

    The span, not the page, is the unit of legacy-font identification, because
    a Unicode heading over a legacy body is ordinary in converted documents.
    """
    spans: list[TextSpan] = []
    run: list[dict] = []

    def flush() -> None:
        if not run:
            return
        text = "".join(char["text"] for char in run)
        raw_font = str(run[0].get("fontname") or "")
        method, quality, notes = _classify_span(text, raw_font)
        legacy = identify_legacy_font(raw_font)
        spans.append(
            TextSpan(
                text=text,
                font=legacy.family if legacy else raw_font,
                raw_font=raw_font,
                size=_span_key(run[0])[1],
                box=BoundingBox.around(_box(char) for char in run) or _box(run[0]),
                method=method,
                quality=quality,
                notes=notes,
            )
        )
        run.clear()

    for char in chars:
        if run and _span_key(char) != _span_key(run[0]):
            flush()
        run.append(char)
    flush()
    return tuple(spans)


def _lines(page: pdfplumber.page.Page) -> tuple[TextLine, ...]:
    try:
        # keep_blank_chars keeps the space characters that are genuinely in the
        # file; _with_word_gaps supplies the ones that are not.
        raw_lines = page.extract_text_lines(strip=True, return_chars=True, keep_blank_chars=True)
    except Exception:  # noqa: BLE001 - one unreadable page must not lose the book
        return ()

    lines: list[TextLine] = []
    for raw in raw_lines:
        spans = _spans(_with_word_gaps(raw.get("chars") or []))
        if not spans:
            continue
        box = BoundingBox.around(span.box for span in spans) or _box(raw)
        lines.append(TextLine(spans=spans, box=box))
    return tuple(lines)


def _page_kind(has_text: bool, image_count: int) -> PageKind:
    if has_text and image_count:
        return PageKind.MIXED
    if has_text:
        return PageKind.TEXT
    if image_count:
        return PageKind.IMAGE
    return PageKind.EMPTY


def _page_notes(
    kind: PageKind, image_count: int, lines: tuple[TextLine, ...], columns: bool
) -> tuple[str, ...]:
    """Why this page is the way it is, in words a reader can be told.

    These reach the interface, so they describe what the reader loses rather
    than what the extractor did.
    """
    notes: list[str] = []
    if kind is PageKind.IMAGE:
        notes.append(
            "This page contains images and no readable text. It has not been recognised, so "
            "nothing on it can be read aloud."
        )
    elif kind is PageKind.MIXED:
        notes.append(
            f"This page contains {image_count} image(s) alongside its text. "
            f"Their content is not described."
        )
    elif kind is PageKind.EMPTY:
        notes.append("This page is blank.")

    if columns:
        notes.append(
            "This page looks like it is laid out in columns. The order the text was read in "
            "may not match the order it is printed in."
        )

    withheld = sum(1 for line in lines if line.quality is QualityState.UNDECODABLE)
    if withheld:
        notes.append(
            f"{withheld} of {len(lines)} lines on this page use a legacy Sinhala font and "
            f"cannot be read yet."
        )
    return tuple(notes)


def extract_page(page: pdfplumber.page.Page, index: int, label: str | None) -> PageExtraction:
    """Everything one page yields, with the notes needed to explain it."""
    image_count = len(page.images)
    lines = _lines(page)
    has_text = any(line.text.strip() for line in lines)
    kind = _page_kind(has_text, image_count)
    columns = has_text and suspects_multiple_columns(page.chars, float(page.width))

    return PageExtraction(
        page_index=index,
        page_label=label,
        width=float(page.width),
        height=float(page.height),
        kind=kind,
        lines=lines,
        image_count=image_count,
        notes=_page_notes(kind, image_count, lines, columns),
    )


def _cause(error: Exception) -> Exception:
    """The original parse failure, unwrapped.

    pdfplumber catches everything pdfminer raises while opening a file and
    re-raises it as one opaque ``PdfminerException``. A password-protected book
    and a file that is not a PDF arrive here identically wrapped, so the
    distinction — which is the difference between "unlock this" and "this is not
    a book" — has to be recovered from the cause.
    """
    if error.args and isinstance(error.args[0], Exception):
        return error.args[0]
    return error


def _open(source: bytes | str | Path, password: str) -> pdfplumber.PDF:
    """Open an untrusted PDF, turning every failure into a reason.

    Validation runs first so that the common rejections carry a message about
    the file rather than about the parser. Any remaining failure to open is a
    rejection: this is untrusted input, and there is no partial success worth
    salvaging from a file pdfminer cannot get a page tree out of.
    """
    if isinstance(source, bytes):
        check_pdf_bytes(source)
        handle: bytes | io.BytesIO | str | Path = io.BytesIO(source)
    else:
        check_pdf_file(source)
        handle = source

    try:
        return pdfplumber.open(handle, password=password)
    except Exception as error:
        cause = _cause(error)
        if isinstance(cause, PDFPasswordIncorrect):
            raise DocumentRejected(
                "This PDF is password-protected. It has to be unlocked before it can be read."
            ) from error
        if isinstance(cause, PDFSyntaxError):
            raise DocumentRejected("This file is not a readable PDF.") from error
        raise DocumentRejected(f"This PDF could not be opened: {cause}") from error


def extract_document(
    source: bytes | str | Path,
    *,
    page_indexes: Iterable[int] | None = None,
    max_pages: int = MAX_PAGES,
    password: str = "",
) -> DocumentExtraction:
    """Extract a PDF, or only the pages named in ``page_indexes``.

    Selecting pages is not an optimisation detail. CLAUDE.md requires the first
    requested section to be produced before the rest of the document, so a
    reader can start listening to chapter one while chapter twelve is still
    being processed. Page indexes are zero-based and returned in ascending
    order; indexes outside the document are ignored rather than raising,
    because a stale request from a client is not a reason to fail a document.
    """
    notes: list[str] = []
    with _open(source, password) as pdf:
        total = len(pdf.pages)
        if total > max_pages:
            raise DocumentRejected(
                f"This document has {total:,} pages, over the {max_pages:,}-page limit."
            )

        labels = page_labels(pdf.doc, total)
        if page_indexes is None:
            wanted = list(range(total))
        else:
            wanted = sorted({index for index in page_indexes if 0 <= index < total})
            if not wanted:
                notes.append("None of the requested pages exist in this document.")

        pages = tuple(extract_page(pdf.pages[index], index, labels[index]) for index in wanted)

    ocr_needed = sum(1 for page in pages if page.kind is PageKind.IMAGE)
    if ocr_needed:
        notes.append(
            f"{ocr_needed} of {len(pages)} extracted page(s) are images with no readable text."
        )
    return DocumentExtraction(pages=pages, notes=tuple(notes))
