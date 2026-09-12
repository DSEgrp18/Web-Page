# The reader API and its background worker: one image, two commands.
#
# They share a process image because they share every line of code that matters
# — the same store, the same pipeline, the same configuration — and building two
# images from one source tree would mean a version skew between the thing that
# accepts an upload and the thing that prepares it. That skew is invisible until
# a document prepared by the old worker is served by the new API.
#
# Deliberately absent: torch and coqui-tts. They add several gigabytes for a
# voice that cannot run without the model bundle, which is mounted rather than
# built in. See infra/README.md for running the real voice.

FROM python:3.13-slim

# psycopg[binary] ships its own libpq, so no build toolchain is needed. Kept
# slim on purpose: every package here is one more thing to patch in an image
# that processes untrusted PDFs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Versions pinned to what the packages declare, installed before the source is
# copied so that editing code does not reinstall the world.
RUN pip install --no-cache-dir \
      "fastapi>=0.115" \
      "python-multipart>=0.0.9" \
      "uvicorn>=0.27" \
      "pdfplumber>=0.11.4" \
      "numpy>=1.26" \
      "psycopg[binary]>=3.2" \
      "psycopg-pool>=3.2" \
      "celery>=5.4" \
      "redis>=5"

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
