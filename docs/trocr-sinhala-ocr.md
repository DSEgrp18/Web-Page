# TrOCR Sinhala OCR

Local Sinhala line recognition for scanned or broken pages, behind the existing
`OcrAdapter`. Tesseract finds line boxes; a TrOCR checkpoint reads each crop.
Private pages stay on this machine.

## Checkpoint aliases

| Alias | Hub id | Pinned revision |
| --- | --- | --- |
| `eshangj` (dev default when engine is `trocr`) | `eshangj/TrOCR-Sinhala-finetuned` | `0c1687ce548c38d4d6b5acc611ec5f91f5a6b412` |
| `ransaka` | `Ransaka/TrOCR-Sinhala` | `922910beb2f14c0c230c89037280cba9601c58cc` |

Neither is proven better on this project's textbooks. Measure both against
Tesseract before changing the compose default.

## Configuration

| Variable | Meaning |
| --- | --- |
| `SINHALA_READER_OCR` | `off` / `broken` / `all` (unchanged) |
| `SINHALA_READER_OCR_ENGINE` | `tesseract` (default) or `trocr` |
| `SINHALA_READER_TROCR_CHECKPOINT` | `eshangj` or `ransaka` |
| `SINHALA_READER_TROCR_MODEL_DIR` | Local download directory (preferred) |
| `SINHALA_READER_TROCR_DEVICE` | `cpu` or `cuda` |

## Download

From the repository root (weights stay under `models/`, which Git ignores):

```bash
hf download eshangj/TrOCR-Sinhala-finetuned \
  --revision 0c1687ce548c38d4d6b5acc611ec5f91f5a6b412 \
  --local-dir models/trocr_sinhala_eshangj

hf download Ransaka/TrOCR-Sinhala \
  --revision 922910beb2f14c0c230c89037280cba9601c58cc \
  --local-dir models/trocr_sinhala_ransaka
```

Local Python (optional extras):

```bash
pip install -e "services/worker[trocr]"
export SINHALA_READER_OCR=broken
export SINHALA_READER_OCR_ENGINE=trocr
export SINHALA_READER_TROCR_CHECKPOINT=eshangj
export SINHALA_READER_TROCR_MODEL_DIR="$PWD/models/trocr_sinhala_eshangj"
```

Compose overlay (installs torch into the API/worker image and mounts the folder):

```bash
export TROCR_MODEL_DIR="$PWD/models/trocr_sinhala_eshangj"
docker compose -f infra/docker-compose.yml -f infra/compose.trocr.yml up --build
```

## Bake-off before flipping the default

Do **not** set `SINHALA_READER_OCR_ENGINE=trocr` in the base compose file until
this comparison is recorded.

1. Collect a small fixed set: known broken textbook pages plus a few
   permission-cleared scanned Sinhala pages with human transcripts.
2. Put page images (or a PDF) and matching `.txt` transcripts under
   `evaluation/ocr/` (gitignored transcripts of private books; commit only
   permission-cleared assets).
3. Run:

```bash
PYTHONPATH=services/worker/src:services/api/src \
  python scripts/ocr_bakeoff.py \
  --pages evaluation/ocr/pages \
  --transcripts evaluation/ocr/transcripts \
  --out evaluation/ocr/bakeoff-results.md
```

4. Compare Tesseract-only, Trocr+`ransaka`, and Trocr+`eshangj` (CER/WER).
5. Spot-listen TTS on a few recognised pages.
6. Record the winner, revisions, and device in the results file. Only then
   change compose defaults.

Until then, Trocr remains an opt-in overlay.
