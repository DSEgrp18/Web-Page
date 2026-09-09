"""Cheap checks that run before a PDF is parsed.

An uploaded PDF is untrusted input. Parsing one is the expensive, attackable
step, so the things that can be decided from the bytes alone are decided first:
is this a PDF at all, and is it small enough to be worth opening. Page count
needs the file open and is checked there.

The limits here are defaults for a library, not a product policy. Real quotas
belong to the API, where the user and their plan are known.
"""

from __future__ import annotations

from pathlib import Path

#: Enough for a scanned textbook, small enough that a worker cannot be filled by
#: one upload. The API is expected to impose its own, lower, per-user limit.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

#: A ceiling on work per document, not a statement about real books.
MAX_PAGES = 3000

_MAGIC = b"%PDF-"

#: Readers tolerate junk before the header, and real files in the wild have it.
_MAGIC_SEARCH_WINDOW = 1024


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
