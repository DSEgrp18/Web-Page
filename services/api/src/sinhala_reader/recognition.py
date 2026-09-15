"""Which pages this process reads from their image, chosen once from configuration.

The same shape as :mod:`.structure` and :mod:`.answers`, and an unrecognised
value stops the process for the same reason: a typo in a deployment variable
must not silently change what readers get.

The default is off. Recognition needs Tesseract installed, which a test run or a
contributor's machine often does not have, and it adds seconds per page to
preparation. The container images install it and compose turns it on.

Unlike structure and answers, nothing here leaves the machine: Tesseract runs
locally. What a deployment still needs to know is that recognised text can be
misread, which the limitations say.
"""

from __future__ import annotations

import os
import shutil

from sinhala_documents.ocr import TESSERACT_ENV, OcrAdapter, OcrMode, TesseractOcr

#: Which pages to recognise: ``off``, ``broken`` or ``all``. See :class:`OcrMode`.
OCR_ENV = "SINHALA_READER_OCR"


def ocr_mode() -> OcrMode:
    """The configured mode.

    Raises:
        ValueError: if the value is not a mode. Deliberately fatal.
    """
    raw = os.environ.get(OCR_ENV, "").strip().lower() or OcrMode.OFF.value
    try:
        return OcrMode(raw)
    except ValueError:
        raise ValueError(
            f"{OCR_ENV}={raw!r} is not a recognition mode this server knows. "
            f"Use one of: {', '.join(mode.value for mode in OcrMode)}."
        ) from None


def build_ocr() -> OcrAdapter | None:
    """The recogniser, or None when recognition is off."""
    if ocr_mode() is OcrMode.OFF:
        return None
    return TesseractOcr()


def _installed() -> bool:
    executable = os.environ.get(TESSERACT_ENV, "").strip() or "tesseract"
    return shutil.which(executable) is not None


def ocr_limitations() -> list[str]:
    """What a deployment should know about the recognition setting, for readiness."""
    mode = ocr_mode()
    if mode is OcrMode.OFF:
        return [
            "Pages are not read from their image. A page whose embedded text cannot be "
            "decoded, holds a hidden copy of itself, or is a scan stays unread. Set "
            f"{OCR_ENV}=broken to recognise those pages with Tesseract.",
        ]
    notes = [
        (
            "Pages whose embedded text cannot be trusted are read from their image"
            if mode is OcrMode.BROKEN
            else "Every page is read from its image"
        )
        + " by Tesseract on this server; nothing is sent elsewhere. Recognised text "
        "can misread letters, and those pages are marked as not checked.",
    ]
    if not _installed():
        notes.append(
            "Tesseract is not installed, so no page can be recognised and those pages "
            "keep their embedded text."
        )
    return notes
