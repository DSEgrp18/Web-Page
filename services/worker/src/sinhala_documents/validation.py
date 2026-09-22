"""Cheap checks that run before a PDF is parsed.

An uploaded PDF is untrusted input. Parsing one is the expensive, attackable
step, so the things that can be decided from the bytes alone are decided first:
is this a PDF at all, and is it small enough to be worth opening. Page count
needs the file open and is checked there.

The limits here are defaults for a library, not a product policy. Real quotas
belong to the API, where the user and their plan are known.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

#: Enough for a scanned textbook, small enough that a worker cannot be filled by
#: one upload. The API is expected to impose its own, lower, per-user limit.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

#: A ceiling on work per document, not a statement about real books.
MAX_PAGES = 3000

#: ``word/document.xml`` is the only potentially large DOCX member read by the
#: current extractor. Bound its decompressed size independently of the archive's
#: compressed upload size so a zip bomb cannot consume the worker's memory.
MAX_DOCX_XML_BYTES = 16 * 1024 * 1024

_MAGIC = b"%PDF-"

#: Readers tolerate junk before the header, and real files in the wild have it.
_MAGIC_SEARCH_WINDOW = 1024

SUPPORTED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class DocumentRejected(Exception):
    """The upload cannot be processed, with a reason fit to show a person."""


def check_pdf_bytes(data: bytes, *, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
    """Reject anything that is not a plausibly sized PDF.

    Passing says only that parsing is worth attempting.
    """
    if not data:
        raise DocumentRejected("The file is empty.")
    if len(data) > max_bytes:
        raise DocumentRejected(
            f"The file is {len(data):,} bytes, over the {max_bytes:,}-byte limit."
        )
    if _MAGIC not in data[:_MAGIC_SEARCH_WINDOW]:
        raise DocumentRejected(
            "The file does not start with a PDF header. Only PDF documents can be read."
        )


def media_type_for(filename: str, data: bytes | None = None) -> str | None:
    """Return a supported media type using the filename as a hint, then bytes.

    Extensionless files occur in scanner and Android share flows. Known
    extensions are still authoritative enough to produce useful mismatch
    errors, while an unknown or missing extension falls back to signatures.
    """
    hinted = SUPPORTED_MEDIA_TYPES.get(Path(filename).suffix.lower())
    if hinted is not None or data is None:
        return hinted
    if _MAGIC in data[:_MAGIC_SEARCH_WINDOW]:
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except BadZipFile:
        return None
    if "[Content_Types].xml" in names and "word/document.xml" in names:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None


def parse_docx_document(source: bytes) -> ElementTree.Element:
    """Read and parse bounded WordprocessingML from an untrusted DOCX."""
    try:
        with ZipFile(BytesIO(source)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise DocumentRejected(
                    "The file extension says DOCX, but its contents are not a Word document."
                )
            member = archive.getinfo("word/document.xml")
            if member.file_size > MAX_DOCX_XML_BYTES:
                raise DocumentRejected("The Word document text is too large to read safely.")
            with archive.open(member) as handle:
                xml = handle.read(MAX_DOCX_XML_BYTES + 1)
    except DocumentRejected:
        raise
    except (BadZipFile, KeyError, OSError, RuntimeError) as error:
        raise DocumentRejected("The Word document is damaged and cannot be read.") from error

    if len(xml) > MAX_DOCX_XML_BYTES:
        raise DocumentRejected("The Word document text is too large to read safely.")
    upper = xml.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise DocumentRejected("The Word document contains unsupported XML declarations.")
    try:
        return ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise DocumentRejected("The Word document is damaged and cannot be read.") from error


def check_document_bytes(data: bytes, filename: str, *, max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Validate a supported PDF, DOCX, PNG or JPEG and return its media type."""
    if not data:
        raise DocumentRejected("The file is empty.")
    if len(data) > max_bytes:
        raise DocumentRejected(
            f"The file is {len(data):,} bytes, over the {max_bytes:,}-byte limit."
        )
    media_type = media_type_for(filename, data)
    if media_type is None:
        raise DocumentRejected("Only PDF, DOCX, PNG and JPEG files can be read.")
    if media_type == "application/pdf":
        check_pdf_bytes(data, max_bytes=max_bytes)
    elif media_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentRejected("The file extension says PNG, but its contents are not a PNG image.")
    elif media_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
        raise DocumentRejected(
            "The file extension says JPEG, but its contents are not a JPEG image."
        )
    elif media_type.endswith("wordprocessingml.document"):
        parse_docx_document(data)
    return media_type


def check_pdf_file(path: str | Path, *, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
    """The same checks without reading the whole file into memory."""
    path = Path(path)
    if not path.is_file():
        raise DocumentRejected(f"{path} is not a file.")
    size = path.stat().st_size
    if size == 0:
        raise DocumentRejected("The file is empty.")
    if size > max_bytes:
        raise DocumentRejected(f"The file is {size:,} bytes, over the {max_bytes:,}-byte limit.")
    with path.open("rb") as handle:
        head = handle.read(_MAGIC_SEARCH_WINDOW)
    if _MAGIC not in head:
        raise DocumentRejected(
            "The file does not start with a PDF header. Only PDF documents can be read."
        )
