"""Document extraction for the Sinhala accessible reader.

The public surface is deliberately small: validate an upload, extract it, and
inspect what came back. Everything else in this package is an implementation
detail of those three steps.
"""

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
from .pdf_extract import extract_document, extract_page
from .pipeline import (
    ReadableDocument,
    ReadablePage,
    ReadableSegment,
    prepare_document,
)
from .validation import (
    MAX_PAGES,
    MAX_UPLOAD_BYTES,
    DocumentRejected,
    check_pdf_bytes,
    check_pdf_file,
)

__all__ = [
    "MAX_PAGES",
    "MAX_UPLOAD_BYTES",
    "BoundingBox",
    "DocumentExtraction",
    "DocumentRejected",
    "ExtractionMethod",
    "PageExtraction",
    "PageKind",
    "QualityState",
    "ReadableDocument",
    "ReadablePage",
    "ReadableSegment",
    "TextLine",
    "TextSpan",
    "check_pdf_bytes",
    "check_pdf_file",
    "extract_document",
    "extract_page",
    "prepare_document",
]
