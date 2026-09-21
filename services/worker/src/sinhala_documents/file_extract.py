"""Extraction adapters for DOCX files and standalone page images."""

from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from .model import BoundingBox, DocumentExtraction, PageExtraction, PageKind, TextLine, TextSpan
from .ocr import NOTE, OcrAdapter, OcrUnavailable, lines_from_words

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx(source: bytes) -> DocumentExtraction:
    """Read paragraph text from a DOCX without executing or rendering its contents."""
    with ZipFile(BytesIO(source)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        image_count = sum(name.startswith("word/media/") for name in archive.namelist())

    lines: list[TextLine] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{_WORD_NS}t")).strip()
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
