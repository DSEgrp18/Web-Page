"""The Sinhala voice as a Modal function.

CLAUDE.md allows exactly one forced split in this system: GPU inference. This
is that split, and nothing else belongs here.

**Only spoken text crosses this boundary.** The reader's PDF, its extracted
text, the document's identity and the reader's identity all stay on our own
server. A student's private textbook never reaches a third-party compute
provider, and that is a property to preserve deliberately rather than an
accident of the current design.

Why Modal rather than a GPU VM, in the numbers measured on 2026-09-10:

- One loaded voice needs 2.34 GB of RAM and generates one segment at a time.
  A VM sized for that sits idle almost always and still costs money at 3 a.m.
- On CPU the model runs at 3.3-3.8x real time. Narrating one 168-page textbook
  takes about 28 hours. On a GPU this should invert; per-second billing then
  charges for the seconds a sentence actually costs.

What this file does **not** solve: cold start. The checkpoint is 5.6 GB and
took 68 s to load on CPU. Scale-to-zero means the first request after an idle
period pays that, which is incompatible with the 5-second first-segment target
in CLAUDE.md. See the README beside this file.

Deploy:

    modal deploy services/tts/deploy/modal_app.py

**Nothing here has been run on Modal yet.** Every number quoted above is a CPU
measurement from this repository; no GPU figure for this model exists. See
``docs/model-inference-manifest.md``.
"""

from __future__ import annotations

import io
import os
import time
import wave
from typing import Any

import modal

# --- what the container is -------------------------------------------------

APP_NAME = "sinhala-reader-tts"

#: The bundle lives on a Volume, never in the image and never in Git. It is
#: 5.6 GB and is delivered out of band; see the README beside this file for the
#: upload procedure. Baking it into the image would push every deploy through
#: 5.6 GB and tie the weights to the application's release cycle, which
#: CLAUDE.md forbids: model weights must not be replaced by an ordinary
#: application deployment.
VOLUME_NAME = "sinhala-xtts-si-female"
MODEL_MOUNT = "/models"
MODEL_DIR = f"{MODEL_MOUNT}/xtts_si_female"

#: Overridable so the GPU can be chosen per deployment without editing code.
#: XTTS-v2 is a small model; the constraint here is latency, not capacity.
GPU = os.environ.get("SINHALA_TTS_MODAL_GPU", "A10G")

#: How long a container stays alive after its last request. Every second here
#: is paid for; every second saved is a reader waiting through a cold load.
#: This is the dial that trades money against the 5-second target, and it
#: should be set from measured usage rather than guessed.
SCALEDOWN_WINDOW = int(os.environ.get("SINHALA_TTS_MODAL_SCALEDOWN", "300"))

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# The pins come from "Runtime dependencies" in the inference manifest, where
# each was established by a failure rather than by preference:
#
#   torch first and separately  - coqui-tts declares neither torch nor
#                                 torchaudio, so installing it alone appears to
#                                 succeed and then fails at model load.
#   cu126, not cu121            - cu121 has no wheels for recent Pythons, and
#                                 pip's error does not say so.
#   transformers >=4.57,<5      - transformers 5 removed isin_mps_friendly,
#                                 which coqui-tts still imports. Unpinned
#                                 installs resolve to 5.x and synthesis dies on
#                                 the first request.
#   no torchcodec               - deliberately absent; the conditioning path
#                                 does not need it.
#
# CLAUDE.md is explicit that pins must not be copied between environments
# untested. These were measured on Windows with Python 3.13 and are **not yet
# verified in this container**. The `verify` entrypoint below exists to do
# exactly that, and until it has been run these are candidates, not facts.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.9.1",
        "torchaudio==2.9.1",
        index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install(
        "coqui-tts==0.27.5",
        "transformers>=4.57,<5",
        "numpy>=1.26",
        "soundfile>=0.12",
    )
    .add_local_python_source("sinhala_tts")
)

app = modal.App(APP_NAME)


# --- the voice -------------------------------------------------------------


@app.cls(
    image=image,
    gpu=GPU,
    volumes={MODEL_MOUNT: volume},
    scaledown_window=SCALEDOWN_WINDOW,
    # A load that takes over a minute must not be mistaken for a hang.
    startup_timeout=15 * 60,
    timeout=10 * 60,
    # Modal serves more readers by adding containers, not by sharing one GPU
    # between concurrent generations - which would exhaust VRAM rather than go
    # faster. The bound exists so a burst cannot open an unbounded number of
    # GPUs; CLAUDE.md asks for concurrency to be bounded and queued.
    max_containers=int(os.environ.get("SINHALA_TTS_MODAL_MAX_CONTAINERS", "4")),
)
class Voice:
    """One container, one loaded checkpoint, one generation at a time.

    ``@modal.enter`` runs once per container rather than once per request,
    which is the "load the model once per worker process" requirement in
    CLAUDE.md expressed in Modal's vocabulary.
    """

    @modal.enter()
    def load(self) -> None:
        from sinhala_tts.adapter import XttsAdapter

        started = time.perf_counter()
        self.adapter = XttsAdapter(MODEL_DIR, device="cuda", max_concurrent=1)

        # Generate once here rather than leaving it to the first reader. The
        # speaker conditioning and any lazy CUDA initialisation happen on this
        # call, and a reader who presses play should not be the one paying for
        # them.
        self.adapter.synthesize("mulika piriksuma", "si-female")
        self.load_seconds = time.perf_counter() - started
        print(f"voice ready in {self.load_seconds:.1f}s on {GPU}", flush=True)

    @modal.method()
    def synthesize(
        self,
        text: str,
        voice_id: str = "si-female",
        settings: dict[str, Any] | None = None,
        document_version: str | None = None,
    ) -> dict[str, Any]:
        """Speak one segment. Returns WAV bytes and the metadata that made them.

        The audio crosses as a WAV rather than as a numpy array, so neither
        side's numpy version can affect the other's and the caller can put the
        bytes straight into its cache without a re-encode.

        Every field of ``SynthesisMetadata`` comes back. CLAUDE.md requires the
        actual model version and synthesis settings to be recorded for every
        generated segment, and the caller cannot record what it is not told.
        """
        from sinhala_tts.adapter import SynthesisSettings

        chosen = SynthesisSettings(**settings) if settings else SynthesisSettings()

        started = time.perf_counter()
        result = self.adapter.synthesize(text, voice_id, chosen, document_version=document_version)
        elapsed = time.perf_counter() - started

        meta = result.metadata
        return {
            "wav": _to_wav(result.samples, result.sample_rate),
            "sample_rate": result.sample_rate,
            "voice_id": meta.voice_id,
            "is_real_model": meta.is_real_model,
            "model_version": meta.model_version,
            "normalizer_version": meta.normalizer_version,
            "device": meta.device,
            "readiness": meta.readiness.value,
            "duration_seconds": meta.duration_seconds,
            "spoken_text": meta.spoken_text,
            "model_text": meta.model_text,
            "settings": vars(chosen),
            # Not part of cache identity. Reported so real-time factor and
            # latency can be monitored, which the MLOps section of CLAUDE.md
            # requires - and which the 15x latency excursion recorded in the
            # manifest would otherwise have hidden.
            "generate_seconds": elapsed,
        }

    @modal.method()
    def readiness(self) -> dict[str, Any]:
        """Is this container actually serving, and what is it serving?

        Process liveness and model readiness are different questions, and
        CLAUDE.md requires them answered separately. A container that is up but
        whose checkpoint failed to load is not ready.
        """
        return {
            "readiness": self.adapter.readiness.value,
            "model_version": self.adapter.model_version,
            "is_real_model": self.adapter.is_real_model,
            "gpu": GPU,
            "load_seconds": getattr(self, "load_seconds", None),
        }


def _to_wav(samples: Any, sample_rate: int) -> bytes:
    """Float samples to 16-bit PCM WAV, clipped rather than wrapped.

    Without the clip, a sample above 1.0 wraps to a large negative value and
    becomes an audible crack. Clipping is audible too, but as the distortion
    ``audio_checks`` already measures rather than as a bang.
    """
    import numpy as np

    pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


# --- verification ----------------------------------------------------------


@app.local_entrypoint()
def verify() -> None:
    """Prove the container works, and measure what nobody has measured yet.

        modal run services/tts/deploy/modal_app.py

    This is the only source of GPU numbers for this project. Everything in the
    inference manifest today is CPU. Until this has been run, no GPU claim
    about this system is true - including the ones in this file's docstring,
    which are predictions.
    """
    from sinhala_tts.audio_checks import check_audio
    from sinhala_tts.regression_sentences import REGRESSION_SENTENCES

    voice = Voice()

    started = time.perf_counter()
    state = voice.readiness.remote()
    cold = time.perf_counter() - started
    print(f"first call, cold start included: {cold:.1f}s")
    print(f"readiness: {state}\n")

    failures = 0
    for case in REGRESSION_SENTENCES:
        out = voice.synthesize.remote(case.text)
        audio, gen = out["duration_seconds"], out["generate_seconds"]

        report = _check(out, check_audio)
        note = "" if not report.problems else "  <-- " + "; ".join(report.problems)
        if report.problems:
            failures += 1

        print(f"{case.name:22} {audio:5.2f}s audio in {gen:6.2f}s  RTF {gen / audio:5.2f}x{note}")

    print(f"\n{len(REGRESSION_SENTENCES) - failures}/{len(REGRESSION_SENTENCES)} pass")


def _check(out: dict[str, Any], check_audio: Any) -> Any:
    """Decode the returned WAV and run the standard audio checks on it.

    Checking the bytes that actually crossed the wire, rather than the array
    inside the container, is the point: a WAV that is well formed can still
    contain silence, and the encode step is where a sample rate or a channel
    count gets lost.
    """
    import numpy as np

    with wave.open(io.BytesIO(out["wav"])) as source:
        frames = source.readframes(source.getnframes())
        rate = source.getframerate()

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    return check_audio(samples, rate, model_text=out["model_text"])
