#!/usr/bin/env python3
"""Smoke-test TrOCR Sinhala OCR the way the reader runs it in Docker.

Fetches one in-distribution line image from the public Sinhala OCR dataset the
checkpoint was trained on, runs TrocrSinhalaOcr with a deterministic full-crop
layout box, and fails unless the recognised text is close to the dataset label.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unicodedata
import urllib.request
from pathlib import Path

#: One row from the public synthetic Sinhala OCR set used to train these models.
DATASET_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=Ransaka%2Fsinhala_synthetic_ocr-large"
    "&config=default&split=train&offset=0&length=1"
)


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


def _load_sample() -> tuple[bytes, str]:
    """PNG bytes and ground-truth text from the Hub dataset viewer API."""
    with urllib.request.urlopen(DATASET_ROWS_URL, timeout=60) as response:
        payload = json.load(response)
    rows = payload.get("rows") or []
    if not rows:
        raise SystemExit(f"No rows returned from {DATASET_ROWS_URL}")
    row = rows[0]["row"]
    text = row.get("text") or row.get("label") or ""
    image = row.get("image") or {}
    source = image.get("src")
    if not text or not source:
        raise SystemExit(f"Unexpected dataset row shape: {sorted(row)}")
    with urllib.request.urlopen(source, timeout=60) as response:
        png = response.read()
    if not png:
        raise SystemExit("Downloaded sample image was empty.")
    return png, text


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

    from PIL import Image

    from sinhala_documents.ocr import OcrAdapter, OcrWord, lines_from_words
    from sinhala_documents.trocr_ocr import TrocrSinhalaOcr

    print(f"Fetching sample from {DATASET_ROWS_URL}", flush=True)
    png, expected = _load_sample()
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
    print(f"sample_size={width}x{height} expected={expected!r}", flush=True)

    class LineLayout(OcrAdapter):
        @property
        def version(self) -> str:
            return "smoke-line/1"

        def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
            return (OcrWord("x", 0, 0, width, height, 1, 1, 1, 1.0),)

    adapter = TrocrSinhalaOcr(
        checkpoint=checkpoint,
        model_dir=model_dir,
        device=device,
        layout=LineLayout(),
    )
    print(f"adapter={adapter.version}", flush=True)
    words = adapter.recognise(png)
    if not words:
        print("OCR returned no words.", file=sys.stderr)
        return 1
    lines = lines_from_words(words, dpi=300, version=adapter.version)
    hypothesis = _normalise(" ".join(line.text for line in lines))
    reference = _normalise(expected)
    cer = _cer(reference, hypothesis)
    print(f"expected={reference!r}")
    print(f"got={hypothesis!r}")
    print(f"cer={cer:.3f}")
    if not any("\u0d80" <= ch <= "\u0dff" for ch in hypothesis):
        print("Recognised text has no Sinhala codepoints.", file=sys.stderr)
        return 1
    if cer > 0.35:
        print(f"CER {cer:.3f} is too high (limit 0.35).", file=sys.stderr)
        return 1
    print("trocr smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
