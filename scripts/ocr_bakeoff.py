#!/usr/bin/env python3
"""Compare Tesseract vs TrOCR checkpoints on a fixed page set.

Expects paired page images and transcripts:

    pages/001.png
    transcripts/001.txt

Reports character and word error rates. Does not invent a compose default —
write the measured winner into docs after reading the table.

Requires Tesseract with Sinhala for the tesseract and trocr (layout) paths.
Trocr rows need torch, transformers, Pillow, and SINHALA_READER_TROCR_MODEL_DIR
(or a Hub download into the HF cache).
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path


def _cer(reference: str, hypothesis: str) -> float:
    """Levenshtein distance / len(reference). Empty reference → 0 if hyp empty else 1."""
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


def _wer(reference: str, hypothesis: str) -> float:
    return _cer(reference.split(), hypothesis.split())


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def _page_text_tesseract(png: bytes) -> str:
    from sinhala_documents.ocr import TesseractOcr, lines_from_words

    words = TesseractOcr().recognise(png)
    lines = lines_from_words(words, dpi=300, version="bakeoff")
    return _normalise("\n".join(line.text for line in lines))


def _page_text_trocr(png: bytes, checkpoint: str, model_dir: str | None, device: str) -> str:
    from sinhala_documents.ocr import lines_from_words
    from sinhala_documents.trocr_ocr import TrocrSinhalaOcr

    adapter = TrocrSinhalaOcr(
        checkpoint=checkpoint,
        model_dir=model_dir,
        device=device,
    )
    words = adapter.recognise(png)
    lines = lines_from_words(words, dpi=300, version=adapter.version)
    return _normalise("\n".join(line.text for line in lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, required=True, help="Directory of page images")
    parser.add_argument(
        "--transcripts",
        type=Path,
        required=True,
        help="Directory of .txt transcripts stem-matched to images",
    )
    parser.add_argument("--out", type=Path, help="Optional markdown report path")
    parser.add_argument(
        "--model-dir-eshangj",
        type=Path,
        default=None,
        help="Local eshangj checkpoint (else Hub/HF cache)",
    )
    parser.add_argument(
        "--model-dir-ransaka",
        type=Path,
        default=None,
        help="Local ransaka checkpoint (else Hub/HF cache)",
    )
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument(
        "--engines",
        default="tesseract,ransaka,eshangj",
        help="Comma list: tesseract, ransaka, eshangj",
    )
    args = parser.parse_args(argv)

    images = sorted(
        p
        for p in args.pages.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    )
    if not images:
        print(f"No page images in {args.pages}", file=sys.stderr)
        return 2

    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    rows: list[str] = [
        "# OCR bake-off",
        "",
        f"Pages: `{args.pages}`",
        f"Device: `{args.device}`",
        "",
        "| Page | Engine | CER | WER |",
        "| --- | --- | ---: | ---: |",
    ]
    totals: dict[str, list[float]] = {e: [] for e in engines}

    for image_path in images:
        transcript_path = args.transcripts / f"{image_path.stem}.txt"
        if not transcript_path.is_file():
            print(f"skip {image_path.name}: no transcript {transcript_path.name}", file=sys.stderr)
            continue
        reference = _normalise(transcript_path.read_text(encoding="utf-8"))
        png = image_path.read_bytes()
        for engine in engines:
            try:
                if engine == "tesseract":
                    hypothesis = _page_text_tesseract(png)
                elif engine == "ransaka":
                    model_dir = str(args.model_dir_ransaka) if args.model_dir_ransaka else None
                    hypothesis = _page_text_trocr(png, "ransaka", model_dir, args.device)
                elif engine == "eshangj":
                    model_dir = str(args.model_dir_eshangj) if args.model_dir_eshangj else None
                    hypothesis = _page_text_trocr(png, "eshangj", model_dir, args.device)
                else:
                    print(f"unknown engine {engine!r}", file=sys.stderr)
                    return 2
                cer = _cer(reference, hypothesis)
                wer = _wer(reference, hypothesis)
                totals[engine].append(cer)
                rows.append(
                    f"| {image_path.name} | {engine} | {cer:.3f} | {wer:.3f} |"
                )
                print(f"{image_path.name}\t{engine}\tCER={cer:.3f}\tWER={wer:.3f}")
            except Exception as error:  # noqa: BLE001 — report and continue the table
                rows.append(f"| {image_path.name} | {engine} | error | {error} |")
                print(f"{image_path.name}\t{engine}\tERROR\t{error}", file=sys.stderr)

    rows.extend(["", "## Means (CER over pages that succeeded)", ""])
    for engine, values in totals.items():
        if values:
            mean = sum(values) / len(values)
            rows.append(f"- **{engine}**: mean CER {mean:.3f} over {len(values)} page(s)")
        else:
            rows.append(f"- **{engine}**: no successful pages")
    rows.append("")
    rows.append(
        "Do not change the compose default until a human has checked this table "
        "and listened to a few synthesised pages."
    )
    report = "\n".join(rows) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
