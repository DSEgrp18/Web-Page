# The API and worker with the real Sinhala voice.
#
# Separate from api.Dockerfile because torch and coqui-tts add several gigabytes
# for something most people running this do not need and cannot use: the voice
# is useless without the model bundle, which is 5.6 GB, is delivered out of band
# by the project owner, and is **mounted** rather than built in.
#
# A teammate who just wants to run the reader should use api.Dockerfile and hear
# the labelled placeholder tone. This image is for whoever has the bundle.
#
# Build it explicitly, because nothing should pull it by accident:
#
#     docker compose -f infra/docker-compose.yml -f infra/compose.voice.yml up --build
#
# See infra/README.md for the mount, and docs/model-inference-manifest.md for
# what the bundle contains and how it was measured.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libsndfile is what soundfile binds to for reading the speaker reference clip.
# Absent, the adapter imports cleanly and fails at the first synthesis, which is
# the worst place to find out.
RUN apt-get update \
 && apt-get install --no-install-recommends -y libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

# torch FIRST and separately, from the CPU index.
#
# Both halves of that are load-bearing, and both are recorded in
# docs/model-inference-manifest.md as things that were learned the hard way.
# coqui-tts declares neither torch nor torchaudio, so installing it alongside
# them appears to succeed and then fails at model load. And the default index
# serves CUDA builds: several gigabytes of GPU runtime for an image that has no
# GPU.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch>=2.5" "torchaudio>=2.5"

# transformers is pinned deliberately. transformers 5 removed isin_mps_friendly,
# which coqui-tts still imports; an unpinned install resolves to 5.x and
# synthesis dies on the first request rather than at install time.
RUN pip install --no-cache-dir \
      "coqui-tts>=0.25" \
      "transformers>=4.57,<5" \
      "soundfile>=0.12"

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

COPY services/api/src /app/services/api/src
COPY services/worker/src /app/services/worker/src
COPY services/tts/src /app/services/tts/src
COPY data/legacy_fonts /app/data/legacy_fonts

ENV PYTHONPATH=/app/services/api/src:/app/services/worker/src:/app/services/tts/src

# The bundle is mounted here read-only. Not copied: an image containing the
# weights could be pushed to a registry, and the CPML position on the underlying
# XTTS-v2 weights is unresolved. .dockerignore excludes models/ so that a COPY
# added here in future fails loudly instead of silently shipping them.
ENV SINHALA_TTS_MODEL_DIR=/models/xtts_si_female

RUN useradd --create-home --uid 10001 reader && chown -R reader:reader /app
USER reader

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "sinhala_reader.serve:app", "--host", "0.0.0.0", "--port", "8000"]
