#!/usr/bin/env bash
# Build the Trocr-enabled API image and prove recognition works inside it.
#
# Used by CI. Downloads the pinned eshangj checkpoint into MODELS_DIR (default
# models/trocr_sinhala_eshangj), builds WITH_TROCR=1, mounts the checkpoint,
# and runs scripts/smoke_trocr_ocr.py in the container.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODELS_DIR="${TROCR_MODEL_DIR:-$ROOT/models/trocr_sinhala_eshangj}"
IMAGE_TAG="${TROCR_SMOKE_IMAGE:-sinhala-reader-trocr-smoke}"
REVISION="0c1687ce548c38d4d6b5acc611ec5f91f5a6b412"
HUB_ID="eshangj/TrOCR-Sinhala-finetuned"

mkdir -p "$MODELS_DIR"

if [[ ! -f "$MODELS_DIR/config.json" || ! -f "$MODELS_DIR/model.safetensors" ]]; then
  echo "Downloading ${HUB_ID}@${REVISION} into ${MODELS_DIR}"
  python3 -m pip install --disable-pip-version-check -q "huggingface_hub>=0.24"
  python3 - <<PY
from huggingface_hub import snapshot_download
snapshot_download(
    "${HUB_ID}",
    revision="${REVISION}",
    local_dir="${MODELS_DIR}",
)
print("download ok")
PY
else
  echo "Using existing checkpoint at ${MODELS_DIR}"
fi

echo "Building ${IMAGE_TAG} with WITH_TROCR=1"
docker build \
  --file infra/api.Dockerfile \
  --build-arg WITH_TROCR=1 \
  --tag "$IMAGE_TAG" \
  .

# fonts-noto-core supplies Noto Sans Sinhala for the synthetic page render.
# Installed at run time so the slim image stays free of font packages unless
# this smoke (or an operator) asks for them.
echo "Running Trocr smoke inside ${IMAGE_TAG}"
docker run --rm \
  --user root \
  -e SINHALA_READER_TROCR_MODEL_DIR=/models/trocr_sinhala \
  -e SINHALA_READER_TROCR_CHECKPOINT=eshangj \
  -e SINHALA_READER_TROCR_DEVICE=cpu \
  -v "${MODELS_DIR}:/models/trocr_sinhala:ro" \
  -v "${ROOT}/scripts/smoke_trocr_ocr.py:/app/scripts/smoke_trocr_ocr.py:ro" \
  "$IMAGE_TAG" \
  bash -lc '
    set -euo pipefail
    apt-get update
    apt-get install --no-install-recommends -y fonts-noto-core
    rm -rf /var/lib/apt/lists/*
    # Drop privileges for the actual recognition: the image is meant to run as
    # reader; root was only needed to install the font for this smoke.
    su -s /bin/bash reader -c 'python /app/scripts/smoke_trocr_ocr.py'
  '

echo "Trocr Docker smoke passed."
