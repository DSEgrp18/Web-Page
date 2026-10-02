# The reader API and its background worker: one image, two commands.
#
# They share a process image because they share every line of code that matters
# — the same store, the same pipeline, the same configuration — and building two
# images from one source tree would mean a version skew between the thing that
# accepts an upload and the thing that prepares it. That skew is invisible until
# a document prepared by the old worker is served by the new API.
#
# Deliberately absent by default: torch and coqui-tts (voice), and torch for
# TrOCR. Voice uses tts.Dockerfile. TrOCR is an optional build-arg
# WITH_TROCR=1 used by compose.trocr.yml, so the slim image stays the default.

FROM python:3.13-slim

ARG WITH_TROCR=0

# psycopg[binary] ships its own libpq, so no build toolchain is needed. Kept
# slim on purpose: every package here is one more thing to patch in an image
# that processes untrusted PDFs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Installed before the source is copied, so that editing code does not reinstall
# the world.
#
# Pinned by infra/constraints/python.txt, the pip freeze of a known-good build.
# The `>=` ranges below say what the code needs; the constraints decide what is
# actually installed, so two builds of the same commit produce the same image.
# Until #79 these were bare floors, which resolve to whatever is newest at build
# time: the voice image, built the same way, broke on an unchanged commit when
# torch 2.9 arrived. The same file pins the voice image, so the packages the two
# images share are the same versions in both.
COPY infra/constraints/python.txt /tmp/constraints.txt
RUN pip install --no-cache-dir -c /tmp/constraints.txt \
      "fastapi>=0.115" \
      "python-multipart>=0.0.9" \
      "uvicorn>=0.27" \
      "pdfplumber>=0.11.4" \
      "numpy>=1.26" \
      "soundfile>=0.12" \
      "psycopg[binary]>=3.2" \
      "psycopg-pool>=3.2" \
      "celery>=5.4" \
      "redis>=5" \
      "langgraph>=1.2"

# Optional TrOCR stack. Built only when compose.trocr.yml / CI smoke sets
# WITH_TROCR=1. torch from the CPU index first, then transformers and Pillow —
# pinned by the same constraints file so a rebuild cannot drift. The checkpoint
# itself is mounted, never copied into the image.
RUN if [ "$WITH_TROCR" = "1" ]; then \
      pip install --no-cache-dir -c /tmp/constraints.txt \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.5" \
      && pip install --no-cache-dir -c /tmp/constraints.txt \
        "transformers>=4.40,<5" \
        "Pillow>=10"; \
    fi

# Tesseract and its Sinhala model, for pages whose embedded text does not match
# what is printed. See services/worker/src/sinhala_documents/ocr.py. It reads
# page images locally: nothing is sent anywhere. TrOCR still needs it for line
# layout when SINHALA_READER_OCR_ENGINE=trocr.
RUN apt-get update \
 && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-sin \
 && rm -rf /var/lib/apt/lists/*

# Three source trees, kept separate the way the packages are. PYTHONPATH rather
# than an install because none of them is published, which is what CI and the
# tests already do.
COPY services/api/src /app/services/api/src
COPY services/worker/src /app/services/worker/src
COPY services/tts/src /app/services/tts/src
COPY data/legacy_fonts /app/data/legacy_fonts

ENV PYTHONPATH=/app/services/api/src:/app/services/worker/src:/app/services/tts/src

# Not root. This process parses PDFs supplied by strangers.
RUN useradd --create-home --uid 10001 reader && chown -R reader:reader /app
USER reader

EXPOSE 8000

# serve, not app: it reads a .env before anything reads the environment. In
# compose the environment is set directly and there is no file, which is exactly
# the case that must keep working.
CMD ["python", "-m", "uvicorn", "sinhala_reader.serve:app", "--host", "0.0.0.0", "--port", "8000"]
