"""Sinhala line recognition with a local TrOCR checkpoint.

TrOCR checkpoints are trained on cropped text lines, not full pages. This
adapter keeps Tesseract for layout (boxes and reading order) and replaces each
line's text with what TrOCR reads from that crop. Private pages stay on this
machine; nothing is sent to a Hub or cloud vision API at recognition time.

Two Hub checkpoints share the same code path. Which one a deployment uses is
configuration, recorded in the adapter version so document provenance and the
audio cache change when the checkpoint does. Neither is assumed better until a
fixed-page bake-off says so — see docs/trocr-sinhala-ocr.md.
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .ocr import (
    OCR_VERSION,
    OcrAdapter,
    OcrUnavailable,
    OcrWord,
    TesseractOcr,
    normalise,
)

#: Alias chosen with ``SINHALA_READER_TROCR_CHECKPOINT``.
CHECKPOINT_ENV = "SINHALA_READER_TROCR_CHECKPOINT"
#: Local directory with a downloaded checkpoint (preferred for offline use).
MODEL_DIR_ENV = "SINHALA_READER_TROCR_MODEL_DIR"
#: ``cpu`` or ``cuda``. Unset means cuda when available, else cpu.
DEVICE_ENV = "SINHALA_READER_TROCR_DEVICE"

#: Pixels of padding around each line crop. Tight crops clip Sinhala marks
#: above and below the letter; too much padding pulls in neighbouring lines.
CROP_PADDING = 4

#: Beam search width used by both Hub model cards.
NUM_BEAMS = 3

#: Bump when crop margins, beams, or how lines are rebuilt change.
TROCR_ADAPTER_VERSION = "1"


@dataclass(frozen=True)
class TrocrCheckpoint:
    """One named Hub checkpoint this adapter knows how to load."""

    alias: str
    hub_id: str
    revision: str

    @property
    def short_revision(self) -> str:
        return self.revision[:7]


CHECKPOINTS: dict[str, TrocrCheckpoint] = {
    "eshangj": TrocrCheckpoint(
        alias="eshangj",
        hub_id="eshangj/TrOCR-Sinhala-finetuned",
        revision="0c1687ce548c38d4d6b5acc611ec5f91f5a6b412",
    ),
    "ransaka": TrocrCheckpoint(
        alias="ransaka",
        hub_id="Ransaka/TrOCR-Sinhala",
        revision="922910beb2f14c0c230c89037280cba9601c58cc",
    ),
}


def resolve_checkpoint(alias: str | None = None) -> TrocrCheckpoint:
    """The configured checkpoint, or the named one.

    Raises:
        ValueError: if the alias is not one this adapter knows.
    """
    raw = (alias if alias is not None else os.environ.get(CHECKPOINT_ENV, "")).strip().lower()
    raw = raw or "eshangj"
    try:
        return CHECKPOINTS[raw]
    except KeyError:
        known = ", ".join(sorted(CHECKPOINTS))
        raise ValueError(
            f"{CHECKPOINT_ENV}={raw!r} is not a TrOCR checkpoint this server knows. "
            f"Use one of: {known}."
        ) from None


def resolve_device(requested: str | None = None) -> str:
    """``cpu`` or ``cuda``, honouring an explicit request when given."""
    raw = (requested if requested is not None else os.environ.get(DEVICE_ENV, "")).strip().lower()
    if raw in {"cpu", "cuda"}:
        return raw
    if raw:
        raise ValueError(
            f"{DEVICE_ENV}={raw!r} is not a device this server knows. Use cpu or cuda."
        )
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


LineRecogniser = Callable[[Any], str]
"""Takes a PIL image crop and returns recognised Sinhala text."""


def _group_line_boxes(
    words: tuple[OcrWord, ...],
) -> list[tuple[tuple[int, int, int], list[OcrWord]]]:
    """Preserve Tesseract's reading order while grouping words into lines."""
    order: list[tuple[int, int, int]] = []
    grouped: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        key = (word.block, word.paragraph, word.line)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(word)
    return [(key, grouped[key]) for key in order]


def _union_box(members: list[OcrWord]) -> tuple[int, int, int, int]:
    left = min(word.left for word in members)
    top = min(word.top for word in members)
    right = max(word.left + word.width for word in members)
    bottom = max(word.top + word.height for word in members)
    return left, top, right, bottom


class TrocrSinhalaOcr(OcrAdapter):
    """Tesseract layout, TrOCR Sinhala text, one checkpoint per process."""

    def __init__(
        self,
        *,
        checkpoint: str | TrocrCheckpoint | None = None,
        model_dir: str | None = None,
        device: str | None = None,
        layout: OcrAdapter | None = None,
        recognise_line: LineRecogniser | None = None,
        open_image: Callable[[bytes], Any] | None = None,
        crop_padding: int = CROP_PADDING,
        num_beams: int = NUM_BEAMS,
    ) -> None:
        if isinstance(checkpoint, TrocrCheckpoint):
            self._checkpoint = checkpoint
        else:
            self._checkpoint = resolve_checkpoint(checkpoint)
        self._model_dir = (
            model_dir
            if model_dir is not None
            else os.environ.get(MODEL_DIR_ENV, "").strip() or None
        )
        self._device_name = resolve_device(device)
        self._layout = layout if layout is not None else TesseractOcr()
        self._recognise_line = recognise_line
        self._open_image = open_image
        self._crop_padding = crop_padding
        self._num_beams = num_beams
        self._processor: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None

    @property
    def checkpoint(self) -> TrocrCheckpoint:
        return self._checkpoint

    @property
    def version(self) -> str:
        layout_version = self._layout.version
        return (
            f"trocr/{self._checkpoint.alias}@{self._checkpoint.short_revision}/"
            f"detect-{layout_version}/beams{self._num_beams}/trocr-{TROCR_ADAPTER_VERSION}/"
            f"ocr-{OCR_VERSION}"
        )

    def _ensure_model(self) -> tuple[Any, Any, Any]:
        if self._recognise_line is not None:
            # Tests inject a line recogniser; nothing is loaded from disk.
            return None, None, None
        if self._model is not None and self._processor is not None and self._torch is not None:
            return self._processor, self._model, self._torch
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        except ImportError as error:
            raise OcrUnavailable(
                "TrOCR needs torch and transformers installed "
                "(pip install 'sinhala-documents[trocr]' or the compose trocr profile)."
            ) from error

        source = self._model_dir or self._checkpoint.hub_id
        revision = None if self._model_dir else self._checkpoint.revision
        try:
            if revision:
                processor = TrOCRProcessor.from_pretrained(source, revision=revision)
                model = VisionEncoderDecoderModel.from_pretrained(source, revision=revision)
            else:
                processor = TrOCRProcessor.from_pretrained(source)
                model = VisionEncoderDecoderModel.from_pretrained(source)
            model.to(self._device_name)
            model.eval()
        except Exception as error:  # noqa: BLE001 — surface any load failure as unavailable
            raise OcrUnavailable(
                f"TrOCR checkpoint {self._checkpoint.alias!r} could not be loaded from "
                f"{source!r}: {error}"
            ) from error

        self._processor = processor
        self._model = model
        self._torch = torch
        return processor, model, torch

    def _read_line(self, crop: Any) -> str:
        if self._recognise_line is not None:
            return normalise(self._recognise_line(crop).strip())

        processor, model, torch = self._ensure_model()
        assert processor is not None and model is not None and torch is not None
        try:
            pixel_values = processor(images=crop, return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(self._device_name)
            with torch.no_grad():
                generated_ids = model.generate(
                    pixel_values,
                    num_beams=self._num_beams,
                    early_stopping=True,
                )
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        except Exception as error:  # noqa: BLE001
            raise OcrUnavailable(f"TrOCR failed on a line crop: {error}") from error
        return normalise(text.strip())

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        layout_words = self._layout.recognise(image_png)
        if not layout_words:
            return ()

        try:
            if self._open_image is not None:
                page = self._open_image(image_png)
            else:
                from PIL import Image

                page = Image.open(io.BytesIO(image_png)).convert("RGB")
        except ImportError as error:
            raise OcrUnavailable(
                "TrOCR needs Pillow to crop line images from the page render."
            ) from error
        except Exception as error:  # noqa: BLE001
            raise OcrUnavailable(
                f"The page image could not be opened for TrOCR: {error}"
            ) from error

        # Warm the model once before the line loop so a missing checkpoint fails
        # the whole page rather than halfway through.
        if self._recognise_line is None:
            self._ensure_model()

        width, height = page.size
        pad = self._crop_padding
        recognised: list[OcrWord] = []
        for (_key, members) in _group_line_boxes(layout_words):
            left, top, right, bottom = _union_box(members)
            crop_box = (
                max(0, left - pad),
                max(0, top - pad),
                min(width, right + pad),
                min(height, bottom + pad),
            )
            if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                continue
            crop = page.crop(crop_box)
            text = self._read_line(crop)
            if not text:
                continue
            # One word spanning the line box: TrOCR returns a line string, and
            # splitting it onto Tesseract's word boxes would invent alignments.
            recognised.append(
                OcrWord(
                    text=text,
                    left=left,
                    top=top,
                    width=max(1, right - left),
                    height=max(1, bottom - top),
                    block=members[0].block,
                    paragraph=members[0].paragraph,
                    line=members[0].line,
                    confidence=-1.0,
                )
            )
        return tuple(recognised)
