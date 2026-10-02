#!/usr/bin/env python3
"""Smoke-test TrOCR Sinhala OCR the way the reader runs it in Docker.

Renders a short Sinhala line, recognises it with TrocrSinhalaOcr (Tesseract
layout + TrOCR text), and fails unless the output is close to the intended
phrase. Intended to run inside the api image built with WITH_TROCR=1, with the
checkpoint mounted at SINHALA_READER_TROCR_MODEL_DIR.
"""

from __future__ import annotations

import io
import os
import sys
import unicodedata
from pathlib import Path


EXPECTED = "ශ්‍රී ලංකා"


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def _cer(reference: str, hypothesis: str) -> float:
    ref = list(reference)
    hyp = list(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, start=1):
        curr = [i]
        for j, hc in enumerate(hyp, start=1):
            ins = curr[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (rc != hc)
            curr.append(min(ins, delete, sub))
        prev = curr
    return prev[-1] / len(ref)


def _sinhala_font() -> str:
    candidates = [
        Path("/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansSinhala-Bold.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansSinhala-Regular.otf"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    # Last resort: any Noto Sinhala the package manager left behind.
    for root in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts")):
        if not root.is_dir():
            continue
        matches = sorted(root.rglob("*Sinhala*.ttf")) + sorted(
            root.rglob("*Sinhala*.otf")
        )
        if matches:
            return str(matches[0])
    raise SystemExit(
        "No Sinhala font found. Install fonts-noto-core (or equivalent) in the image."
    )


def _render_page(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(_sinhala_font(), 64)
    # Wide page so Tesseract's page segmentation has room to find one clean line.
    image = Image.new("RGB", (900, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> int:
    model_dir = os.environ.get("SINHALA_READER_TROCR_MODEL_DIR", "").strip()
    if not model_dir or not Path(model_dir).is_dir():
        print(
            "SINHALA_READER_TROCR_MODEL_DIR must point at a downloaded TrOCR checkpoint.",
            file=sys.stderr,
        )
        return 2
    if not (Path(model_dir) / "config.json").is_file():
        print(
            f"{model_dir} does not look like a TrOCR checkpoint (no config.json).",
            file=sys.stderr,
        )
        return 2

    checkpoint = (
        os.environ.get("SINHALA_READER_TROCR_CHECKPOINT", "eshangj").strip()
        or "eshangj"
    )
    device = os.environ.get("SINHALA_READER_TROCR_DEVICE", "cpu").strip() or "cpu"

    from sinhala_documents.ocr import lines_from_words
    from sinhala_documents.trocr_ocr import TrocrSinhalaOcr

    png = _render_page(EXPECTED)
    adapter = TrocrSinhalaOcr(
        checkpoint=checkpoint,
        model_dir=model_dir,
        device=device,
    )
    print(f"adapter={adapter.version}", flush=True)
    words = adapter.recognise(png)
    if not words:
        print("OCR returned no words.", file=sys.stderr)
        return 1
    lines = lines_from_words(words, dpi=300, version=adapter.version)
    hypothesis = _normalise(" ".join(line.text for line in lines))
    reference = _normalise(EXPECTED)
    cer = _cer(reference, hypothesis)
    print(f"expected={reference!r}")
    print(f"got={hypothesis!r}")
    print(f"cer={cer:.3f}")
    # Printed Sinhala from a clean synthetic line should be near-exact. Allow a
    # little room for ZWJ / spacing variants without accepting gibberish.
    if cer > 0.35:
        print(f"CER {cer:.3f} is too high (limit 0.35).", file=sys.stderr)
        return 1
    if not any("\u0d80" <= ch <= "\u0dff" for ch in hypothesis):
        print("Recognised text has no Sinhala codepoints.", file=sys.stderr)
        return 1
    print("trocr smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
