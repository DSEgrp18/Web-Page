"""The synthesis adapter: ``synthesize(text, voice_id, settings) -> audio + metadata``.

This is the boundary CLAUDE.md asks for. Everything above it — the API, the
worker, the reader — deals in text and audio segments and never imports torch,
never knows where the checkpoint lives, and never needs a GPU to be tested.

Two implementations sit behind the same interface:

* :class:`XttsAdapter` loads the real Sinhala checkpoint. It needs the model
  bundle and the inference stack, so it cannot run in CI.
* :class:`DevelopmentAdapter` produces an obvious placeholder tone. It exists so
  the application can be built and tested without the 5.6 GB bundle.

**The development adapter must never be mistaken for the model.** Its output is
a tone, not speech; every result it produces carries ``is_real_model=False`` and
a voice id prefixed ``development-``; and it refuses to run unless explicitly
constructed. CLAUDE.md is explicit that mock audio must never be presented as
real model output, so the metadata makes the distinction impossible to lose.

What this deliberately does not promise
---------------------------------------
**In-flight generation cannot be cancelled.** A torch forward pass runs to
completion inside a single call; there is no safe way to interrupt it in
process. Cancellation here means work that has not started is refused and a
result whose caller has gone away is discarded. A timeout bounds how long a
caller *waits*, not how long the GPU is busy. Saying otherwise would be a
comfortable lie that shows up later as a stuck worker.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from .audio_checks import EXPECTED_SAMPLE_RATE, AudioReport, check_audio
from .normalize import (
    MODEL_INPUT_CHAR_LIMIT,
    NORMALIZER_VERSION,
    exceeds_model_limit,
    is_speakable,
    to_model_input,
    to_speech_text,
)

# Files a usable voice bundle must contain. The tokenizer and the speaker
# reference are not interchangeable, so a partial bundle is a hard failure
# rather than something to work around.
REQUIRED_BUNDLE_FILES = ("config.json", "model.pth", "vocab.json", "reference.wav")

DEFAULT_MODEL_DIR_ENV = "SINHALA_TTS_MODEL_DIR"


class ReadinessState(StrEnum):
    """Process liveness and model readiness are different questions.

    CLAUDE.md requires them distinguished: a worker can be alive and answering
    health checks while holding no model at all, and it can hold a model while
    running far slower than the service promises. Collapsing these into one
    boolean is how an outage gets reported as healthy.
    """

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    READY = "ready"
    #: Serving, but not on the hardware the latency targets assume. The owner's
    #: decision on 2026-09-09 was to keep the CPU fallback and make it visible;
    #: this is what "visible" means at the adapter boundary.
    DEGRADED = "degraded"
    FAILED = "failed"


class SynthesisError(Exception):
    """Base class. Every failure here should tell an operator what to do."""


class ModelNotReadyError(SynthesisError):
    pass


class TextNotSpeakableError(SynthesisError):
    """The text normalises to nothing a model could say."""


class TextTooLongError(SynthesisError):
    """Longer than the model will reliably speak; the segmenter should have split it."""


class SynthesisTimeoutError(SynthesisError):
    """Timed out *waiting for a slot*, not mid-generation. See the module docstring."""


@dataclass(frozen=True)
class SynthesisSettings:
    """Generation settings, recorded with every segment produced.

    Defaults are the ones measured as working, not the ones in ``config.json``.
    `Xtts.inference` carries its own defaults and the config's values do not
    apply unless passed, so `repetition_penalty` is 10.0 here — what actually
    runs — rather than the 5.0 the config documents.
    """

    language: str = "en"
    temperature: float = 0.65
    speed: float = 1.0
    repetition_penalty: float = 10.0
    top_k: int = 50
    top_p: float = 0.85
    length_penalty: float = 1.0
    do_sample: bool = True

    def fingerprint(self) -> str:
        """Stable identity for cache keys. Changing any setting changes it."""
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SynthesisMetadata:
    """What produced this audio. Recorded per segment, not per release.

    CLAUDE.md requires the actual model version and synthesis settings on every
    generated segment, and requires cache identity to include the text hash,
    document version, model version, normalizer version, voice, and settings.
    Both are satisfied here so a cached segment can be traced back to exactly
    what made it.
    """

    voice_id: str
    is_real_model: bool
    model_version: str
    settings: SynthesisSettings
    normalizer_version: str
    device: str
    readiness: ReadinessState
    sample_rate: int
    duration_seconds: float
    spoken_text: str
    model_text: str
    generated_at: str
    document_version: str | None = None
    synthesis_seconds: float = 0.0
    audio_report: AudioReport | None = None

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.model_text.encode("utf-8")).hexdigest()[:16]

    def cache_key(self) -> str:
        """Identity of this audio for caching.

        Deliberately includes the normalizer version: a change to how numbers
        are written out changes the speech, and serving the old audio afterwards
        would be a silent regression. Also includes whether the model was real,
        so development tones can never be served as narration.
        """
        parts = [
            self.text_hash,
            self.document_version or "-",
            self.model_version,
            self.normalizer_version,
            self.voice_id,
            self.settings.fingerprint(),
            "real" if self.is_real_model else "development",
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SynthesisResult:
    samples: np.ndarray
    sample_rate: int
    metadata: SynthesisMetadata


def resolve_model_dir(explicit: str | Path | None = None) -> Path:
    """Locate the voice bundle through configuration, never a hard-coded path.

    The bundle is delivered out of band and is not in Git, so the location is
    configuration. A missing or partial bundle fails loudly here rather than
    somewhere deep inside the loader.
    """
    candidate = explicit or os.environ.get(DEFAULT_MODEL_DIR_ENV)
    if not candidate:
        raise SynthesisError(
            f"No model bundle configured. Set {DEFAULT_MODEL_DIR_ENV} to the directory "
            "holding config.json, model.pth, vocab.json and reference.wav. The bundle is "
            "delivered out of band and is never in Git."
        )
    path = Path(candidate).expanduser().resolve()
    missing = [name for name in REQUIRED_BUNDLE_FILES if not (path / name).is_file()]
    if missing:
        raise SynthesisError(
            f"Model bundle at {path} is incomplete, missing: {', '.join(missing)}. "
            "All four files belong together; the tokenizer and speaker reference are "
            "not interchangeable."
        )
    return path


def bundle_version(model_dir: Path) -> str:
    """A cheap, stable identifier for the loaded artifact.

    Hashes the small files in full and the checkpoint's size and modification
    time rather than its 5.6 GB of content: a full digest would add minutes to
    every worker start. It is enough to notice that the bundle changed, which is
    what cache identity needs; a release still records the full checksum from
    the manifest.
    """
    digest = hashlib.sha256()
    for name in ("config.json", "vocab.json"):
        digest.update((model_dir / name).read_bytes())
    checkpoint = model_dir / "model.pth"
    stat = checkpoint.stat()
    digest.update(f"{stat.st_size}:{int(stat.st_mtime)}".encode())
    return digest.hexdigest()[:16]


class TtsAdapter(ABC):
    """`synthesize(text, voice_id, settings) -> audio + metadata`."""

    @property
    @abstractmethod
    def readiness(self) -> ReadinessState: ...

    @property
    @abstractmethod
    def is_real_model(self) -> bool:
        """False for anything that does not produce speech from the checkpoint."""

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Identity of what would generate audio right now."""

    def voice_id_for(self, voice_id: str) -> str:
        """The voice id that will be *recorded*, which need not be the one asked for.

        The development adapter answers a request for ``si-female`` with
        ``development-si-female``, and that difference has to reach the cache key
        rather than being applied only on the way out.
        """
        return voice_id

    def cache_key(
        self,
        text: str,
        voice_id: str,
        settings: SynthesisSettings | None = None,
        *,
        document_version: str | None = None,
    ) -> str:
        """The key :meth:`synthesize` would produce, without generating anything.

        Caching is worthless if finding out whether audio exists costs a
        synthesis. This builds the same identity from the same parts — there is
        one implementation of the key, in :meth:`SynthesisMetadata.cache_key`,
        and both paths go through it.

        The text guards run here too, so an unspeakable segment is refused at
        lookup rather than at generation.
        """
        spoken, model_text = self.prepare_text(text)
        return SynthesisMetadata(
            voice_id=self.voice_id_for(voice_id),
            is_real_model=self.is_real_model,
            model_version=self.model_version,
            settings=settings or SynthesisSettings(),
            normalizer_version=NORMALIZER_VERSION,
            device="",
            readiness=self.readiness,
            sample_rate=0,
            duration_seconds=0.0,
            spoken_text=spoken,
            model_text=model_text,
            generated_at="",
            document_version=document_version,
        ).cache_key()

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        settings: SynthesisSettings | None = None,
        *,
        document_version: str | None = None,
        timeout_seconds: float | None = None,
    ) -> SynthesisResult: ...

    def prepare_text(self, text: str) -> tuple[str, str]:
        """Display text to (spoken text, model input), with the guards applied.

        Shared by every implementation so the development adapter exercises the
        same validation the real one does. A text that would be rejected in
        production must be rejected in development, or the placeholder stops
        being a useful stand-in.
        """
        spoken = to_speech_text(text)
        model_text = to_model_input(text)
        if not is_speakable(model_text):
            raise TextNotSpeakableError(
                f"{text!r} normalises to {model_text!r}, which has nothing to say. "
                "Synthesising it would produce a silent clip that a cache would store "
                "as valid audio and a listener would experience as a skipped sentence."
            )
        if exceeds_model_limit(model_text):
            raise TextTooLongError(
                f"{len(model_text)} characters of model input exceeds the model's "
                f"{MODEL_INPUT_CHAR_LIMIT}-character limit. Nothing splits this for us: "
                "Xtts.inference only splits when enable_text_splitting is set, which it "
                "is not. Segment the text before synthesising it."
            )
        return spoken, model_text


class DevelopmentAdapter(TtsAdapter):
    """A labelled placeholder. **Its output is a tone, not speech.**

    It exists so the reader, the API, and the job pipeline can be built and
    tested without the checkpoint. Every result says ``is_real_model=False`` and
    carries a ``development-`` voice id, and the cache key includes that flag, so
    placeholder audio can never be served in place of narration.

    It applies the same text validation as the real adapter, so a segment that
    would be rejected in production is rejected here too.
    """

    #: Something obviously synthetic. A pleasant tone would be worse: it might
    #: pass a casual listen and reach a demo.
    TONE_HZ = 440.0

    def __init__(self, *, sample_rate: int = EXPECTED_SAMPLE_RATE) -> None:
        self._sample_rate = sample_rate

    @property
    def readiness(self) -> ReadinessState:
        return ReadinessState.READY

    @property
    def is_real_model(self) -> bool:
        return False

    @property
    def model_version(self) -> str:
        return "development-adapter"

    def voice_id_for(self, voice_id: str) -> str:
        return f"development-{voice_id}"

    def synthesize(
        self,
        text: str,
        voice_id: str,
        settings: SynthesisSettings | None = None,
        *,
        document_version: str | None = None,
        timeout_seconds: float | None = None,
    ) -> SynthesisResult:
        settings = settings or SynthesisSettings()
        spoken, model_text = self.prepare_text(text)

        # Length follows the measured duration model, so timing-dependent code
        # above the adapter sees something plausible rather than a fixed clip.
        from .audio_checks import expected_duration_seconds

        duration = expected_duration_seconds(model_text)
        started = time.perf_counter()
        t = np.linspace(0.0, duration, int(self._sample_rate * duration), endpoint=False)
        samples = (0.2 * np.sin(2 * np.pi * self.TONE_HZ * t)).astype(np.float32)
        elapsed = time.perf_counter() - started

        metadata = SynthesisMetadata(
            voice_id=self.voice_id_for(voice_id),
            is_real_model=self.is_real_model,
            model_version=self.model_version,
            settings=settings,
            normalizer_version=NORMALIZER_VERSION,
            device="none",
            readiness=ReadinessState.READY,
            sample_rate=self._sample_rate,
            duration_seconds=duration,
            spoken_text=spoken,
            model_text=model_text,
            generated_at=datetime.now(UTC).isoformat(),
            document_version=document_version,
            synthesis_seconds=elapsed,
            audio_report=check_audio(samples, self._sample_rate, model_text=model_text),
        )
        return SynthesisResult(samples, self._sample_rate, metadata)


@dataclass
class _LoadedModel:
    model: Any
    config: Any
    device: str
    half: bool
    conditioning: tuple[Any, Any]
    version: str


class XttsAdapter(TtsAdapter):
    """The real Sinhala checkpoint.

    The model is loaded **once per process**, on first use, and generation is
    serialised: XTTS does not fit twice in the VRAM this runs on, and two
    concurrent generations would exhaust it. Concurrency is bounded here rather
    than left to the caller, because the caller cannot see the GPU.

    Import of torch and coqui-tts is deferred to :meth:`load` so that this module
    can be imported, and the rest of the adapter tested, on a machine with
    neither.
    """

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        device: str | None = None,
        precision: str = "fp16",
        max_concurrent: int = 1,
    ) -> None:
        self._model_dir_setting = model_dir
        self._requested_device = device
        self._precision = precision
        self._state = ReadinessState.NOT_LOADED
        self._loaded: _LoadedModel | None = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._failure: str | None = None

    @property
    def readiness(self) -> ReadinessState:
        return self._state

    @property
    def is_real_model(self) -> bool:
        return True

    @property
    def model_version(self) -> str:
        """The loaded bundle's version, loading it if that has not happened yet.

        A cache key must describe the model that would actually generate the
        audio, so this cannot answer before the bundle is known. Workers load at
        start-up, so in practice the load has already happened.
        """
        self.load()
        assert self._loaded is not None
        return self._loaded.version

    @property
    def failure_reason(self) -> str | None:
        return self._failure

    def load(self) -> None:
        """Load once. Safe to call repeatedly and from several threads."""
        with self._load_lock:
            if self._loaded is not None:
                return
            self._state = ReadinessState.LOADING
            try:
                self._loaded = self._load_bundle()
            except Exception as error:  # noqa: BLE001 - recorded, then re-raised
                self._state = ReadinessState.FAILED
                self._failure = str(error)
                raise
            self._state = (
                ReadinessState.DEGRADED
                if self._loaded.device == "cpu" and self._requested_device != "cpu"
                else ReadinessState.READY
            )

    def _load_bundle(self) -> _LoadedModel:
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        model_dir = resolve_model_dir(self._model_dir_setting)

        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(
            config,
            checkpoint_path=str(model_dir / "model.pth"),
            vocab_path=str(model_dir / "vocab.json"),
            use_deepspeed=False,
        )
        model.eval()

        device = self._requested_device or ("cuda" if torch.cuda.is_available() else "cpu")
        half = False
        if device == "cuda":
            try:
                model.cuda()
                if self._precision == "fp16":
                    model.half()
                    half = True
            except torch.cuda.OutOfMemoryError:
                # Kept, but never silent: readiness becomes DEGRADED and every
                # segment records device="cpu". CLAUDE.md forbids quietly moving
                # overloaded inference to CPU; the agreed resolution was to keep
                # the fallback and surface it.
                torch.cuda.empty_cache()
                model.float().cpu()
                device = "cpu"

        conditioning = self._compute_conditioning(model, config, model_dir)
        return _LoadedModel(
            model=model,
            config=config,
            device=device,
            half=half,
            conditioning=conditioning,
            version=bundle_version(model_dir),
        )

    @staticmethod
    def _compute_conditioning(model: Any, config: Any, model_dir: Path) -> tuple[Any, Any]:
        """Speaker latents, computed once per process and reused.

        The reference clip is read with soundfile rather than through
        ``get_conditioning_latents(audio_path=...)``: from torch 2.9 that path
        routes audio IO through torchcodec, which needs FFmpeg's native
        libraries installed system-wide.
        """
        import soundfile as sf
        import torch

        wav, rate = sf.read(str(model_dir / "reference.wav"), dtype="float32", always_2d=True)
        audio = torch.from_numpy(wav.mean(axis=1)).unsqueeze(0)

        conditioning_rate = 22050
        if rate != conditioning_rate:
            import torchaudio

            audio = torchaudio.functional.resample(audio, rate, conditioning_rate)
            rate = conditioning_rate

        # Device *and* dtype must match: a float32 reference against a
        # half-precision model fails deep in the GPT forward pass, with an error
        # naming neither dtype nor this function.
        parameter = next(model.parameters())
        audio = audio.to(device=parameter.device, dtype=parameter.dtype)

        gpt_cond_latent = model.get_gpt_cond_latents(
            audio,
            rate,
            length=getattr(config, "gpt_cond_len", 30),
            chunk_length=getattr(config, "gpt_cond_chunk_len", 4),
        )
        return gpt_cond_latent, model.get_speaker_embedding(audio, rate)

    def synthesize(
        self,
        text: str,
        voice_id: str,
        settings: SynthesisSettings | None = None,
        *,
        document_version: str | None = None,
        timeout_seconds: float | None = None,
    ) -> SynthesisResult:
        import torch

        settings = settings or SynthesisSettings()
        spoken, model_text = self.prepare_text(text)

        self.load()
        loaded = self._loaded
        if loaded is None:  # pragma: no cover - load() raises before this
            raise ModelNotReadyError(self._failure or "model failed to load")

        # Bounds how long a caller waits for a slot. It does NOT bound the
        # generation already running: a torch forward pass cannot be interrupted
        # in process, and pretending otherwise would produce stuck workers that
        # report a timeout while still holding the GPU.
        acquired = self._slots.acquire(timeout=timeout_seconds)
        if not acquired:
            raise SynthesisTimeoutError(
                f"waited {timeout_seconds}s for a synthesis slot and none became free; "
                "the worker is saturated, not stuck"
            )
        try:
            started = time.perf_counter()
            with torch.inference_mode():
                out = loaded.model.inference(
                    model_text,
                    settings.language,
                    *loaded.conditioning,
                    speed=settings.speed,
                    temperature=settings.temperature,
                    repetition_penalty=settings.repetition_penalty,
                    top_k=settings.top_k,
                    top_p=settings.top_p,
                    length_penalty=settings.length_penalty,
                    do_sample=settings.do_sample,
                )
            elapsed = time.perf_counter() - started
        finally:
            self._slots.release()

        wav = out["wav"]
        if isinstance(wav, torch.Tensor):
            wav = wav.detach().to(device="cpu", dtype=torch.float32).numpy()
        samples = np.asarray(wav, dtype=np.float32)

        sample_rate = int(
            getattr(loaded.config.model_args, "output_sample_rate", EXPECTED_SAMPLE_RATE)
        )
        report = check_audio(samples, sample_rate, model_text=model_text)

        metadata = SynthesisMetadata(
            voice_id=voice_id,
            is_real_model=True,
            model_version=loaded.version,
            settings=settings,
            normalizer_version=NORMALIZER_VERSION,
            device=loaded.device,
            readiness=self._state,
            sample_rate=sample_rate,
            duration_seconds=len(samples) / sample_rate if sample_rate else 0.0,
            spoken_text=spoken,
            model_text=model_text,
            generated_at=datetime.now(UTC).isoformat(),
            document_version=document_version,
            synthesis_seconds=elapsed,
            audio_report=report,
        )
        return SynthesisResult(samples, sample_rate, metadata)


@dataclass(frozen=True)
class HealthReport:
    """Liveness and readiness, answered separately."""

    alive: bool
    readiness: ReadinessState
    device: str | None = None
    detail: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def serving(self) -> bool:
        return self.readiness in (ReadinessState.READY, ReadinessState.DEGRADED)


def health(adapter: TtsAdapter) -> HealthReport:
    """Report an adapter's state without touching the model.

    The process being alive says nothing about whether a model is loaded, and a
    loaded model says nothing about whether it is on the hardware the latency
    targets assume. `DEGRADED` is serving-but-slow and must reach the reader as
    a status, not sit in a log line.
    """
    device = getattr(adapter, "_loaded", None)
    device_name = device.device if device is not None else None
    notes: list[str] = []
    if adapter.readiness is ReadinessState.DEGRADED:
        notes.append(
            "Running on CPU after the GPU could not hold the model. Narration will be "
            "much slower than usual; tell the reader rather than letting them wait."
        )
    if isinstance(adapter, DevelopmentAdapter):
        notes.append(
            "Development adapter: output is a placeholder tone, not speech. It must "
            "never be served as narration."
        )
    return HealthReport(
        alive=True,
        readiness=adapter.readiness,
        device=device_name,
        detail=getattr(adapter, "failure_reason", None),
        notes=notes,
    )


def with_settings(result: SynthesisResult, **changes: object) -> SynthesisSettings:
    """Derive settings from a previous result, for regenerating a segment."""
    return replace(result.metadata.settings, **changes)  # type: ignore[arg-type]
