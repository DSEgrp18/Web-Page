"""Google Cloud Vision document OCR with a bounded local fallback.

The provider supplies words and geometry; it never rewrites, completes, or
"smooths" them with a generative model.  Pages leave this machine only when
this adapter is selected explicitly.  Every provider failure is contained to
the affected page and falls back once to mixed Sinhala/English Tesseract.
"""

from __future__ import annotations

import logging
import os
import time
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .model import PageExtraction
from .ocr import (
    OcrAdapter,
    OcrPageResult,
    OcrUnavailable,
    OcrWord,
    TesseractOcr,
    normalise,
)

LOCATION_ENV = "SINHALA_READER_VISION_LOCATION"
TIMEOUT_ENV = "SINHALA_READER_VISION_TIMEOUT_SECONDS"
MAX_PAGES_ENV = "SINHALA_READER_CLOUD_OCR_MAX_PAGES"

DEFAULT_LOCATION = "global"
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_PAGES = 500
RENDER_DPI = 200
MAX_IMAGES_PER_REQUEST = 16
MAX_ENCODED_BYTES = 8 * 1024 * 1024
MAX_INLINE_PDF_BYTES = 8 * 1024 * 1024
LANGUAGE_HINTS = ("si", "en")
ADAPTER_VERSION = "1"
CLEANUP_VERSION = "1"

log = logging.getLogger(__name__)


def _positive_float(value: str, default: float) -> float:
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _encoded_size(data: bytes) -> int:
    return 4 * ((len(data) + 2) // 3)


def _has_letter_or_number(text: str) -> bool:
    return any(unicodedata.category(character)[0] in {"L", "N"} for character in text)


def clean_words(
    words: tuple[OcrWord, ...], *, page_width: int, page_height: int
) -> tuple[OcrWord, ...]:
    """Remove only lines that cannot carry readable document content.

    English, Sinhala, digits, Roman labels, years, marks and exam codes all
    contain a letter or number and therefore survive.  Confidence alone never
    deletes a body line: provider confidence is not calibrated correctness.
    """
    grouped: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        grouped.setdefault((word.block, word.paragraph, word.line), []).append(word)

    kept: list[OcrWord] = []
    for members in grouped.values():
        while members and not _has_letter_or_number(members[0].text):
            members = members[1:]
        while members and not _has_letter_or_number(members[-1].text):
            members = members[:-1]
        if not members or not any(_has_letter_or_number(word.text) for word in members):
            continue

        text = "".join(word.text for word in members)
        credible = sum(character.isalnum() for character in text)
        positive = sorted(word.confidence for word in members if word.confidence >= 0)
        confidence = positive[len(positive) // 2] if positive else 100.0
        top = min(word.top for word in members)
        bottom = max(word.top + word.height for word in members)
        in_margin = top < page_height * 0.025 or bottom > page_height * 0.975
        # A one-character, nearly-zero-confidence mark on the physical edge is
        # scanner noise.  This deliberately cannot remove a question number,
        # Roman label, year, code, or word.
        if in_margin and credible <= 1 and confidence < 10:
            continue
        kept.extend(members)
    return tuple(kept)


def _break_after(symbol: Any) -> bool:
    properties = getattr(symbol, "property", None)
    detected = getattr(properties, "detected_break", None)
    kind = getattr(detected, "type_", getattr(detected, "type", None))
    # Proto enum values: EOL_SURE_SPACE=3, LINE_BREAK=5.  Names keep the parser
    # testable with lightweight fakes and resilient across protobuf wrappers.
    name = getattr(kind, "name", str(kind))
    return kind in {3, 5} or name in {"EOL_SURE_SPACE", "LINE_BREAK"}


def _vertices(box: Any) -> tuple[int, int, int, int]:
    vertices = list(getattr(box, "vertices", ()) or ())
    if not vertices:
        vertices = list(getattr(box, "normalized_vertices", ()) or ())
    if not vertices:
        return 0, 0, 1, 1
    xs = [float(getattr(vertex, "x", 0) or 0) for vertex in vertices]
    ys = [float(getattr(vertex, "y", 0) or 0) for vertex in vertices]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return round(left), round(top), max(1, round(right - left)), max(1, round(bottom - top))


def words_from_annotation(
    annotation: Any,
    *,
    target_width: float | None = None,
    target_height: float | None = None,
) -> tuple[tuple[OcrWord, ...], int, int]:
    """Convert Vision's page/block/paragraph/word hierarchy to our words."""
    pages = list(getattr(annotation, "pages", ()) or ())
    if not pages:
        return (), 1, 1
    page = pages[0]
    source_width = max(1, int(getattr(page, "width", 1) or 1))
    source_height = max(1, int(getattr(page, "height", 1) or 1))
    scale_x = (target_width / source_width) if target_width is not None else 1.0
    scale_y = (target_height / source_height) if target_height is not None else 1.0

    found: list[OcrWord] = []
    for block_number, block in enumerate(getattr(page, "blocks", ()) or (), start=1):
        for paragraph_number, paragraph in enumerate(
            getattr(block, "paragraphs", ()) or (), start=1
        ):
            line_number = 1
            for item in getattr(paragraph, "words", ()) or ():
                symbols = list(getattr(item, "symbols", ()) or ())
                text = normalise("".join(str(getattr(symbol, "text", "")) for symbol in symbols))
                if not text:
                    continue
                left, top, width, height = _vertices(getattr(item, "bounding_box", None))
                confidence = float(getattr(item, "confidence", -1.0) or -1.0)
                if 0 <= confidence <= 1:
                    confidence *= 100
                found.append(
                    OcrWord(
                        text=text,
                        left=round(left * scale_x),
                        top=round(top * scale_y),
                        width=max(1, round(width * scale_x)),
                        height=max(1, round(height * scale_y)),
                        block=block_number,
                        paragraph=paragraph_number,
                        line=line_number,
                        confidence=confidence,
                    )
                )
                if symbols and _break_after(symbols[-1]):
                    line_number += 1

    width = round(source_width * scale_x)
    height = round(source_height * scale_y)
    return clean_words(tuple(found), page_width=width, page_height=height), width, height


class GoogleVisionOcr(OcrAdapter):
    """Cloud Vision first, one bounded local Tesseract fallback per page."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        fallback: OcrAdapter | None = None,
        location: str | None = None,
        timeout: float | None = None,
        max_pages: int | None = None,
    ) -> None:
        self._client = client
        self._vision: Any | None = None
        self._fallback = fallback or TesseractOcr(language="sin+eng")
        self._location = (
            location if location is not None else os.environ.get(LOCATION_ENV, "").strip()
        ) or DEFAULT_LOCATION
        self._timeout = timeout or _positive_float(
            os.environ.get(TIMEOUT_ENV, ""), DEFAULT_TIMEOUT_SECONDS
        )
        self._max_pages = max_pages or _positive_int(
            os.environ.get(MAX_PAGES_ENV, ""), DEFAULT_MAX_PAGES
        )

    @property
    def version(self) -> str:
        hints = "+".join(LANGUAGE_HINTS)
        return (
            f"google-vision/document-text-detection/v{ADAPTER_VERSION}/{hints}/"
            f"dpi{RENDER_DPI}/cleanup-{CLEANUP_VERSION}/fallback-{self._fallback.version}"
        )

    def _api(self) -> tuple[Any, Any]:
        if self._client is not None and self._vision is not None:
            return self._client, self._vision
        try:
            from google.cloud import vision_v1 as vision
        except ImportError as error:
            raise OcrUnavailable(
                "Google Vision OCR needs the google-cloud-vision package."
            ) from error
        if self._client is None:
            endpoint = (
                "vision.googleapis.com"
                if self._location == "global"
                else f"{self._location}-vision.googleapis.com"
            )
            try:
                self._client = vision.ImageAnnotatorClient(
                    client_options={"api_endpoint": endpoint}
                )
            except Exception as error:  # noqa: BLE001 - ADC failures use local OCR
                raise OcrUnavailable(
                    f"Google Vision credentials are unavailable: {error}"
                ) from error
        self._vision = vision
        return self._client, vision

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        results = self._recognise_images([(0, image_png)])
        result = results.get(0)
        if result is not None:
            return result.words
        return self._fallback.recognise(image_png)

    def _image_request(self, vision: Any, content: bytes) -> Any:
        return vision.AnnotateImageRequest(
            image=vision.Image(content=content),
            features=[
                vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            ],
            image_context=vision.ImageContext(language_hints=list(LANGUAGE_HINTS)),
        )

    @staticmethod
    def _error(response: Any) -> str:
        return str(getattr(getattr(response, "error", None), "message", "") or "")

    def _recognise_images(self, images: list[tuple[int, bytes]]) -> dict[int, OcrPageResult]:
        client, vision = self._api()
        requests = [self._image_request(vision, content) for _, content in images]
        try:
            response = client.batch_annotate_images(
                request={"requests": requests}, retry=None, timeout=self._timeout
            )
        except Exception as error:  # noqa: BLE001 - provider errors fall back locally
            raise OcrUnavailable(
                f"Google Vision image OCR failed: {type(error).__name__}"
            ) from error

        results: dict[int, OcrPageResult] = {}
        for (page_index, _content), item in zip(
            images, getattr(response, "responses", ()) or (), strict=False
        ):
            if self._error(item):
                continue
            words, _, _ = words_from_annotation(getattr(item, "full_text_annotation", None))
            if words:
                results[page_index] = OcrPageResult(words, RENDER_DPI)
        return results

    def _recognise_pdf(
        self, source: bytes, pages: list[PageExtraction]
    ) -> dict[int, OcrPageResult]:
        client, vision = self._api()
        request = vision.AnnotateFileRequest(
            input_config=vision.InputConfig(content=source, mime_type="application/pdf"),
            features=[
                vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            ],
            image_context=vision.ImageContext(language_hints=list(LANGUAGE_HINTS)),
            pages=[page.page_index + 1 for page in pages],
        )
        try:
            response = client.batch_annotate_files(
                request={"requests": [request]}, retry=None, timeout=self._timeout
            )
        except Exception as error:  # noqa: BLE001 - provider errors fall back locally
            raise OcrUnavailable(f"Google Vision PDF OCR failed: {type(error).__name__}") from error

        files = list(getattr(response, "responses", ()) or ())
        items = list(getattr(files[0], "responses", ()) or ()) if files else []
        results: dict[int, OcrPageResult] = {}
        for page, item in zip(pages, items, strict=False):
            if self._error(item):
                continue
            words, _, _ = words_from_annotation(
                getattr(item, "full_text_annotation", None),
                target_width=page.width,
                target_height=page.height,
            )
            if words:
                # Coordinates were scaled to PDF points above.
                results[page.page_index] = OcrPageResult(words, 72)
        return results

    @staticmethod
    def _batches(images: list[tuple[int, bytes]]) -> Iterable[list[tuple[int, bytes]]]:
        batch: list[tuple[int, bytes]] = []
        encoded = 0
        for item in images:
            size = _encoded_size(item[1])
            if batch and (
                len(batch) >= MAX_IMAGES_PER_REQUEST or encoded + size > MAX_ENCODED_BYTES
            ):
                yield batch
                batch = []
                encoded = 0
            batch.append(item)
            encoded += size
        if batch:
            yield batch

    def recognise_document(
        self,
        source: bytes | str | Path,
        pages: Iterable[PageExtraction],
        *,
        dpi: int,
        render: Callable[..., bytes],
    ) -> dict[int, OcrPageResult]:
        selected = list(pages)
        cloud_pages = selected[: self._max_pages]
        started = time.monotonic()
        results: dict[int, OcrPageResult] = {}
        rendered: dict[int, bytes] = {}

        try:
            if (
                isinstance(source, bytes)
                and 0 < len(cloud_pages) <= 5
                and len(source) <= MAX_INLINE_PDF_BYTES
            ):
                results.update(self._recognise_pdf(source, cloud_pages))
            else:
                images: list[tuple[int, bytes]] = []
                for page in cloud_pages:
                    content = render(source, page.page_index, dpi=RENDER_DPI)
                    rendered[page.page_index] = content
                    images.append((page.page_index, content))
                for batch in self._batches(images):
                    try:
                        results.update(self._recognise_images(batch))
                    except OcrUnavailable:
                        # Do not retry the provider. Each page below falls back once.
                        continue
        except OcrUnavailable:
            # Authentication, deadline, quota, or malformed provider response.
            # The loop below contains the failure per page.
            pass

        fallback_count = 0
        for page in selected:
            if page.page_index in results:
                continue
            content = rendered.get(page.page_index)
            if content is None:
                content = render(source, page.page_index, dpi=RENDER_DPI)
            try:
                words = self._fallback.recognise(content)
            except OcrUnavailable:
                continue
            results[page.page_index] = OcrPageResult(words, RENDER_DPI)
            fallback_count += 1

        log.info(
            "OCR pages=%d cloud=%d fallback=%d duration_seconds=%.3f",
            len(selected),
            len(selected) - fallback_count,
            fallback_count,
            time.monotonic() - started,
        )
        return results
