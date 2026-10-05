"""Which pages this process reads from their image, chosen once from configuration.

The same shape as :mod:`.structure` and :mod:`.answers`, and an unrecognised
value stops the process for the same reason: a typo in a deployment variable
must not silently change what readers get.

The default is off. Recognition needs an engine installed, which a test run or a
contributor's machine often does not have, and it adds seconds per page to
preparation. The container images install Tesseract and compose turns recognition
on for broken pages.

Tesseract and TrOCR run locally. Google Vision is an explicit external mode;
readiness discloses that pages leave the machine and that Tesseract is its
bounded fallback.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from sinhala_documents.google_vision_ocr import GoogleVisionOcr
from sinhala_documents.ocr import (
    TESSDATA_DIR_ENV,
    TESSERACT_ENV,
    OcrAdapter,
    OcrMode,
    TesseractOcr,
)
from sinhala_documents.trocr_ocr import (
    CHECKPOINT_ENV,
    CHECKPOINTS,
    DEVICE_ENV,
    MODEL_DIR_ENV,
    TrocrSinhalaOcr,
    resolve_checkpoint,
    resolve_device,
)

#: Which pages to recognise: ``off``, ``broken`` or ``all``. See :class:`OcrMode`.
OCR_ENV = "SINHALA_READER_OCR"
#: Which recogniser to use when recognition is on.
ENGINE_ENV = "SINHALA_READER_OCR_ENGINE"

ENGINES = frozenset({"google-vision", "tesseract", "trocr"})


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


def ocr_engine() -> str:
    """``google-vision``, ``tesseract`` or ``trocr``.

    Raises:
        ValueError: if the value is not an engine. Deliberately fatal.
    """
    raw = os.environ.get(ENGINE_ENV, "").strip().lower() or "tesseract"
    if raw not in ENGINES:
        raise ValueError(
            f"{ENGINE_ENV}={raw!r} is not a recognition engine this server knows. "
            f"Use one of: {', '.join(sorted(ENGINES))}."
        )
    return raw


def trocr_checkpoint_alias() -> str:
    """The configured TrOCR checkpoint alias (validated even when unused)."""
    return resolve_checkpoint().alias


def build_ocr() -> OcrAdapter | None:
    """The recogniser, or None when recognition is off."""
    if ocr_mode() is OcrMode.OFF:
        return None
    engine = ocr_engine()
    if engine == "tesseract":
        return TesseractOcr()
    if engine == "google-vision":
        return GoogleVisionOcr()
    # Validate device early so a typo fails at start-up, not on the first page.
    resolve_device()
    return TrocrSinhalaOcr(checkpoint=trocr_checkpoint_alias())


def _tesseract_installed() -> bool:
    executable = os.environ.get(TESSERACT_ENV, "").strip() or "tesseract"
    return shutil.which(executable) is not None


def _tesseract_has_sinhala() -> bool:
    """Whether the selected executable can actually load the Sinhala model."""
    executable = os.environ.get(TESSERACT_ENV, "").strip() or "tesseract"
    if shutil.which(executable) is None:
        return False
    tessdata_dir = os.environ.get(TESSDATA_DIR_ENV, "").strip()
    prefix = ["--tessdata-dir", tessdata_dir] if tessdata_dir else []
    try:
        result = subprocess.run(
            [executable, *prefix, "--list-langs"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    languages = result.stdout.decode("utf-8", "replace").splitlines()
    return result.returncode == 0 and "sin" in {item.strip() for item in languages}


def _trocr_deps_installed() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _google_vision_ready() -> bool:
    """Whether the client and ADC credentials can be resolved without a request."""
    try:
        import google.auth
        from google.cloud import vision_v1  # noqa: F401

        google.auth.default(scopes=("https://www.googleapis.com/auth/cloud-platform",))
    except Exception:  # noqa: BLE001 - readiness reports every dependency/ADC failure alike
        return False
    return True


def ocr_limitations() -> list[str]:
    """What a deployment should know about the recognition setting, for readiness."""
    from .queue import uses_celery

    mode = ocr_mode()
    if mode is OcrMode.OFF:
        return [
            "Pages are not read from their image. A page whose embedded text cannot be "
            "decoded, holds a hidden copy of itself, or is a scan stays unread. Set "
            f"{OCR_ENV}=broken to recognise those pages with Tesseract or TrOCR.",
        ]

    engine = ocr_engine()
    scope = (
        "Pages whose embedded text cannot be trusted are read from their image"
        if mode is OcrMode.BROKEN
        else "Every page is read from its image"
    )

    if engine == "tesseract":
        notes = [
            f"{scope} by Tesseract on this server; nothing is sent elsewhere. "
            "Recognised text can misread letters, and those pages are marked as not checked.",
        ]
        if not _tesseract_installed():
            notes.append(
                "Tesseract is not installed, so no page can be recognised and those pages "
                "keep their embedded text."
            )
        elif not _tesseract_has_sinhala():
            notes.append(
                "Tesseract is installed but its Sinhala language data (`sin`) is missing, "
                "so no Sinhala page can be recognised. Install tesseract-ocr-sin or set "
                "SINHALA_READER_TESSDATA_DIR to a complete tessdata directory."
            )
        return notes

    if engine == "google-vision":
        notes = [
            f"{scope} by Google Cloud Vision, so selected document pages are sent to "
            "Google for external processing. Provider failures fall back once to local "
            "Sinhala and English Tesseract. Recognised text can misread letters and is "
            "marked as not checked; no generative model rewrites document words.",
        ]
        if not _google_vision_ready():
            notes.append(
                "Google Vision or its Application Default Credentials are unavailable, so "
                "recognition currently uses the local Tesseract fallback."
            )
        if not _tesseract_installed():
            notes.append(
                "Tesseract is not installed, so Google Vision failures cannot fall back locally."
            )
        elif not _tesseract_has_sinhala():
            notes.append(
                "Tesseract's Sinhala language data (`sin`) is missing, so Google Vision "
                "failures cannot recognise Sinhala locally."
            )
        return notes

    checkpoint = resolve_checkpoint()
    notes = [
        f"{scope} by TrOCR ({checkpoint.alias}: {checkpoint.hub_id}) on this server, "
        "with Tesseract used only to find line boxes; nothing is sent elsewhere. "
        "Recognised text can misread letters, and those pages are marked as not checked. "
        "Pick a checkpoint with "
        f"{CHECKPOINT_ENV} ({', '.join(sorted(CHECKPOINTS))}); measure both before "
        "treating either as default.",
    ]
    if not _tesseract_installed():
        notes.append(
            "Tesseract is not installed, so TrOCR has no line layout and those pages "
            "keep their embedded text."
        )
    elif not _tesseract_has_sinhala():
        notes.append(
            "Tesseract's Sinhala language data (`sin`) is missing, so TrOCR cannot find "
            "line layout. Install tesseract-ocr-sin or configure a complete tessdata directory."
        )
    if uses_celery():
        notes.append(
            "The `ocr` field in this response describes the API process only. Page "
            "recognition during preparation runs in the worker, which may have Tesseract "
            "even when this process does not."
        )
    if not _trocr_deps_installed():
        notes.append(
            "torch, transformers, and Pillow are not installed, so TrOCR cannot run and "
            "those pages keep their embedded text."
        )
    model_dir = os.environ.get(MODEL_DIR_ENV, "").strip()
    if model_dir and not os.path.isdir(model_dir):
        notes.append(
            f"{MODEL_DIR_ENV}={model_dir!r} is not a directory, so TrOCR cannot load "
            "its checkpoint."
        )
    device = resolve_device()
    notes.append(f"TrOCR device is {device} ({DEVICE_ENV}).")
    return notes
