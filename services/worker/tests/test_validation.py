"""Rejecting uploads before they are parsed.

Parsing is the expensive, attackable step. Everything decidable from the bytes
should be decided first, and every rejection has to carry a reason a person can
act on — a reader who is told "invalid file" learns nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pdf_fixtures import build_pdf, sinhala_page

from sinhala_documents import (
    DocumentRejected,
    check_pdf_bytes,
    check_pdf_file,
    extract_document,
)


def test_a_real_pdf_passes() -> None:
    check_pdf_bytes(build_pdf([sinhala_page()]))


def test_an_empty_upload_is_refused() -> None:
    with pytest.raises(DocumentRejected, match="empty"):
        check_pdf_bytes(b"")


def test_a_file_that_is_not_a_pdf_is_refused_by_its_header() -> None:
    with pytest.raises(DocumentRejected, match="PDF header"):
        check_pdf_bytes(b"PK\x03\x04 this is a zip file" + b"\x00" * 2000)


def test_a_pdf_with_junk_before_the_header_is_accepted() -> None:
    """Real files in the wild have it, and every reader tolerates it."""
    check_pdf_bytes(b"leading junk\r\n" + build_pdf([sinhala_page()]))


def test_an_oversized_upload_is_refused_with_both_numbers() -> None:
    with pytest.raises(DocumentRejected) as error:
        check_pdf_bytes(b"%PDF-1.7" + b"\x00" * 5000, max_bytes=1000)
    assert "1,000-byte limit" in str(error.value)


def test_the_same_checks_apply_to_a_path(tmp_path: Path) -> None:
    path = tmp_path / "book.pdf"
    path.write_bytes(build_pdf([sinhala_page()]))
    check_pdf_file(path)

    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(DocumentRejected, match="empty"):
        check_pdf_file(empty)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DocumentRejected, match="not a file"):
        check_pdf_file(tmp_path / "absent.pdf")


def test_extraction_validates_without_being_asked() -> None:
    """Validation that callers have to remember is validation that gets skipped."""
    with pytest.raises(DocumentRejected, match="PDF header"):
        extract_document(b"not a pdf" + b"\x00" * 2000)


def test_a_password_protected_pdf_says_so() -> None:
    """pdfplumber wraps every open failure identically.

    Without unwrapping the cause, "unlock this book" and "this is not a book"
    would reach the reader as the same message.
    """
    with pytest.raises(DocumentRejected, match="password-protected"):
        extract_document(build_pdf([sinhala_page()], encrypted=True))
