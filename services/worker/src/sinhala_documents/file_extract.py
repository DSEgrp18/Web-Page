"""Extraction adapters for DOCX files, pasted text and standalone page images."""

from __future__ import annotations

from io import BytesIO
from xml.etree.ElementTree import Element
from zipfile import ZipFile

from .model import BoundingBox, DocumentExtraction, PageExtraction, PageKind, TextLine, TextSpan
from .ocr import NOTE, OcrAdapter, OcrUnavailable, lines_from_words
from .validation import parse_docx_document

#: About how long one section of pasted text is, in characters. Pasted text has
#: no pages, so it is cut into sections of about this size at line breaks.
SECTION_CHARACTERS = 3_000

_PASTED_NOTE = "Pasted text. It is divided into sections of about 3,000 characters, not pages."

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT = f"{_WORD_NS}t"
_PARAGRAPH = f"{_WORD_NS}p"
_TAB = f"{_WORD_NS}tab"
_BREAKS = {f"{_WORD_NS}br", f"{_WORD_NS}cr"}
_TEXT_BOX = f"{_WORD_NS}txbxContent"


def _paragraph_text(paragraph: Element) -> str:
    """Preserve Word text separators without visiting nested paragraphs twice."""
    parts: list[str] = []

    def visit(node: Element) -> None:
        for child in node:
            tag = child.tag
            if tag in {_TEXT_BOX, _PARAGRAPH}:
                # ``root.iter(w:p)`` visits nested text-box paragraphs in their
                # own turn. Descending here would fuse and duplicate their text.
                continue
            if tag == _TEXT:
                parts.append(child.text or "")
            elif tag == _TAB:
                parts.append("\t")
            elif tag in _BREAKS:
                parts.append("\n")
            else:
                visit(child)

    visit(paragraph)
    return "".join(parts).strip()


def extract_docx(source: bytes) -> DocumentExtraction:
    """Read paragraph text from a DOCX without executing or rendering its contents."""
    root = parse_docx_document(source)
    with ZipFile(BytesIO(source)) as archive:
        image_count = sum(name.startswith("word/media/") for name in archive.namelist())

    lines: list[TextLine] = []
    for paragraph in root.iter(_PARAGRAPH):
        text = _paragraph_text(paragraph)
        if not text:
            continue
        top = 36.0 + len(lines) * 18.0
        box = BoundingBox(36.0, top, 576.0, top + 16.0)
        span = TextSpan(text=text, font="", raw_font="docx", size=12.0, box=box)
        lines.append(TextLine(spans=(span,), box=box))

    kind = (
        PageKind.MIXED
        if lines and image_count
        else PageKind.TEXT
        if lines
        else PageKind.IMAGE
        if image_count
        else PageKind.EMPTY
    )
    notes = [
        "Text was extracted from the Word document. Original Word page layout is not "
        "available in the reader."
    ]
    if image_count:
        notes.append(f"This Word document contains {image_count} image(s) that are not described.")
    page = PageExtraction(0, None, 612.0, 792.0, kind, tuple(lines), image_count, tuple(notes))
    return DocumentExtraction(pages=(page,), notes=tuple(notes))


def extract_text(source: bytes) -> DocumentExtraction:
    """Split pasted text into sections at line breaks, keeping every character.

    There is no font to go by, so each line is classified from its text alone,
    the way a PDF span with an unknown font is: text that looks like a legacy
    encoding is marked for review and never converted, and another script is
    withheld.
    """
    from .pdf_extract import _classify_span

    text = source.decode("utf-8")
    sections: list[list[str]] = [[]]
    size = 0
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            continue
        if size and size + len(line) > SECTION_CHARACTERS:
            sections.append([])
            size = 0
        sections[-1].append(line)
        size += len(line)

    pages = []
    for index, section in enumerate(s for s in sections if s):
        lines = []
        for number, line in enumerate(section):
            method, quality, notes, _ = _classify_span(line, "")
            top = 36.0 + number * 18.0
            box = BoundingBox(36.0, top, 576.0, top + 16.0)
            span = TextSpan(
                text=line,
                font="",
                raw_font="text",
                size=12.0,
                box=box,
                method=method,
                quality=quality,
                notes=notes,
            )
            lines.append(TextLine(spans=(span,), box=box))
        pages.append(
            PageExtraction(
                index, None, 612.0, 792.0, PageKind.TEXT, tuple(lines), 0, (_PASTED_NOTE,)
            )
        )
    return DocumentExtraction(pages=tuple(pages), notes=(_PASTED_NOTE,))


def extract_image(
    source: bytes, adapter: OcrAdapter | None, *, dpi: int = 300
) -> DocumentExtraction:
    """Treat an image as one page and recognise Sinhala text with the OCR adapter."""
    notes: list[str] = []
    lines: tuple[TextLine, ...] = ()
    if adapter is None:
        notes.append(
            "Optical character recognition is disabled, so text in this image was not read."
        )
    else:
        try:
            words = adapter.recognise(source)
            lines = lines_from_words(words, dpi=dpi, version=adapter.version)
            notes.append(NOTE)
            if not lines:
                notes.append(
                    "Optical character recognition did not find readable text in this image."
                )
        except OcrUnavailable as error:
            notes.append(
                f"Text in this image could not be read by optical character recognition: {error}"
            )
    page = PageExtraction(
        page_index=0,
        page_label=None,
        width=612.0,
        height=792.0,
        kind=PageKind.MIXED if lines else PageKind.IMAGE,
        lines=lines,
        image_count=1,
        notes=tuple(notes),
    )
    return DocumentExtraction(pages=(page,), notes=tuple(notes))
