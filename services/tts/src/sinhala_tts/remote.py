"""The voice on a remote GPU, behind one HTTPS endpoint.

The reader's API runs on a CPU machine, where the checkpoint speaks at two to
ten times slower than real time. The same checkpoint runs on a GPU on Modal
(``deploy/modal_app.py``), and this adapter is how the API uses it: the same
``synthesize(text, voice_id, settings) -> audio + metadata`` as the local
adapter, so nothing above it changes.

What crosses the wire is only spoken text and the settings that speak it. The
reader's PDF, the document's identity and the reader's identity stay on the
API's server, as ``deploy/modal_app.py`` requires.

Faithful to the local adapter on purpose:

- **The same text guards run here first**, so an unspeakable or over-long
  segment is refused before a GPU is woken for it.
- **The pipeline's prepared text is sent**, so the remote voice reads a
  heading's "1.1" as the pipeline decided and the cache key computed here
  matches the audio that comes back.
- **The returned WAV is checked here** with the same audio checks, on the
  bytes that actually crossed the wire.
- **Readiness is the remote's**, fetched at start-up (``load``), and the
  model version it reports is what cache keys carry.
- **Concurrency is bounded here**, so a burst of requests cannot open more
  GPUs than ``max_concurrent``; a caller that cannot get a slot in time gets
  ``SynthesisTimeoutError``, exactly as with the local model.

A cold start (no warm container) takes a minute or more; ``load`` waits for it,
in the background thread the API starts it on.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .adapter import (
    DEFAULT_VOICE,
    ModelNotReadyError,
    ReadinessState,
    SynthesisError,
    SynthesisMetadata,
    SynthesisResult,
    SynthesisSettings,
    SynthesisTimeoutError,
    TextNotSpeakableError,
    TextTooLongError,
    TtsAdapter,
    VoiceUnavailableError,
    check_voice,
)
from .audio_checks import check_audio
from .normalize import NORMALIZER_VERSION
from .overrides import normalizer_version

#: How long to wait for the remote voice to answer, cold start included.
STATUS_TIMEOUT_SECONDS = 15 * 60
#: How long one segment may take, a cold start included.
SYNTHESIS_TIMEOUT_SECONDS = 10 * 60
#: How often a request for a voice the remote did not have may ask again, so a
#: clip added to the remote's bundle is found without restarting this server.
VOICE_RECHECK_SECONDS = 60.0


@dataclass(frozen=True)
class _Remote:
    """What the remote voice said about itself. ``device`` is read by ``health``."""

    device: str
    version: str
    #: Voice id to the id its audio is recorded under. An endpoint from before
    #: voices existed reports none and has only the default.
    voices: dict[str, str]


class RemoteVoiceAdapter(TtsAdapter):
    """The real checkpoint on a remote GPU. See the module docstring."""

    def __init__(self, url: str, key: str, *, max_concurrent: int = 4) -> None:
        # HTTPS, or this machine's own loopback (the tests' stand-in server).
        if not (url.startswith("https://") or url.startswith("http://127.0.0.1:")):
            raise ValueError(f"the remote voice must be reached over HTTPS, not {url!r}")
        if not key:
            raise ValueError("the remote voice needs its key")
        self._url = url
        self._key = key
        self._state = ReadinessState.NOT_LOADED
        self._loaded: _Remote | None = None
        self._failure: str | None = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._voices_checked = 0.0

    # -- state ------------------------------------------------------------

    @property
    def readiness(self) -> ReadinessState:
        return self._state

    @property
    def is_real_model(self) -> bool:
        return True

    @property
    def model_version(self) -> str:
        """The remote model's version, asking for it if it is not known yet."""
        self.load()
        assert self._loaded is not None
        return self._loaded.version

    @property
    def failure_reason(self) -> str | None:
        return self._failure

    def load(self) -> None:
        """Ask the remote voice whether it is serving, once. Waits out a cold start."""
        with self._load_lock:
            if self._loaded is not None:
                return
            self._state = ReadinessState.LOADING
            try:
                answer = self._post({"status": True}, STATUS_TIMEOUT_SECONDS)
                state = ReadinessState(answer.get("readiness", "failed"))
                if state not in (ReadinessState.READY, ReadinessState.DEGRADED):
                    raise ModelNotReadyError(f"the remote voice reports {state.value}")
                remote_normalizer = answer.get("normalizer_version")
                if remote_normalizer != NORMALIZER_VERSION:
                    # The text is prepared here and spoken there; two versions
                    # would put audio under a cache key that does not describe it.
                    raise ModelNotReadyError(
                        f"the remote voice normalises text as version {remote_normalizer!r}, "
                        f"this server as {NORMALIZER_VERSION!r}; deploy them together"
                    )
                self._loaded = _Remote(
                    device=str(answer.get("device") or "remote"),
                    version=str(answer["model_version"]),
                    voices=_voices(answer),
                )
                self._voices_checked = time.monotonic()
            except Exception as error:  # noqa: BLE001 - recorded, then re-raised
                self._state = ReadinessState.FAILED
                self._failure = str(error)
                raise
            self._state = state

    def voices(self) -> dict[str, str]:
        """What the remote reported. Never waits for it: readiness calls this."""
        return dict(self._loaded.voices) if self._loaded else {}

    def voice_id_for(self, voice_id: str) -> str:
        """As the base class, after asking the remote again if the voice was missing."""
        check_voice(voice_id)
        self.load()
        loaded = self._loaded
        assert loaded is not None
        if voice_id not in loaded.voices and (
            time.monotonic() - self._voices_checked >= VOICE_RECHECK_SECONDS
        ):
            self._voices_checked = time.monotonic()
            answer = self._post({"status": True}, STATUS_TIMEOUT_SECONDS)
            self._loaded = _Remote(loaded.device, loaded.version, _voices(answer))
        return super().voice_id_for(voice_id)

    # -- speech -----------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice_id: str,
        settings: SynthesisSettings | None = None,
        *,
        document_version: str | None = None,
        timeout_seconds: float | None = None,
        prepared: tuple[str, str] | None = None,
    ) -> SynthesisResult:
        settings = settings or SynthesisSettings()
        spoken, model_text = self.prepare_text(text, prepared=prepared)
        self.load()
        recorded = self.voice_id_for(voice_id)

        if not self._slots.acquire(timeout=timeout_seconds):
            raise SynthesisTimeoutError(
                f"waited {timeout_seconds}s for a synthesis slot and none became free; "
                "the remote voice is saturated, not stuck"
            )
        try:
            started = time.perf_counter()
            answer = self._post(
                {
                    "text": text,
                    "voice_id": voice_id,
                    "settings": vars(settings),
                    "document_version": document_version,
                    "prepared": [spoken, model_text],
                },
                SYNTHESIS_TIMEOUT_SECONDS,
            )
            elapsed = time.perf_counter() - started
        finally:
            self._slots.release()

        samples, sample_rate = _decode_wav(base64.b64decode(answer["wav"]))
        version = str(answer.get("model_version") or "")
        if self._loaded is not None and version and version != self._loaded.version:
            # Redeployed since start-up: later cache keys describe the new one.
            self._loaded = _Remote(self._loaded.device, version, self._loaded.voices)
        # What the remote says it spoke in. Differs from `recorded` only if the
        # clip was replaced there since this server last asked.
        spoken_in = str(answer.get("voice_id") or recorded)
        loaded = self._loaded
        assert loaded is not None
        if spoken_in != loaded.voices.get(voice_id):
            self._loaded = _Remote(
                loaded.device, loaded.version, {**loaded.voices, voice_id: spoken_in}
            )
            loaded = self._loaded

        metadata = SynthesisMetadata(
            voice_id=spoken_in,
            is_real_model=True,
            model_version=loaded.version,
            settings=settings,
            normalizer_version=normalizer_version(),
            device=loaded.device,
            readiness=self._state,
            sample_rate=sample_rate,
            duration_seconds=len(samples) / sample_rate if sample_rate else 0.0,
            spoken_text=spoken,
            model_text=model_text,
            generated_at=datetime.now(UTC).isoformat(),
            document_version=document_version,
            synthesis_seconds=elapsed,
            audio_report=check_audio(samples, sample_rate, model_text=model_text),
        )
        return SynthesisResult(samples, sample_rate, metadata)

    # -- transport --------------------------------------------------------

    def _post(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https or loopback, checked in __init__
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = _detail(error)
            if error.code == 422 and detail.startswith("TextNotSpeakableError"):
                raise TextNotSpeakableError(detail) from error
            if error.code == 422 and detail.startswith("TextTooLongError"):
                raise TextTooLongError(detail) from error
            if error.code == 422 and detail.startswith("VoiceUnavailableError"):
                raise VoiceUnavailableError(detail) from error
            if error.code == 401:
                raise SynthesisError(
                    "the remote voice refused this server's key; check SINHALA_READER_TTS_KEY "
                    "against the swara-tts-key secret on Modal"
                ) from error
            raise SynthesisError(f"the remote voice answered {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SynthesisError(f"the remote voice could not be reached: {error}") from error


def _voices(answer: dict[str, Any]) -> dict[str, str]:
    reported = answer.get("voices")
    if not isinstance(reported, dict):
        return {DEFAULT_VOICE: DEFAULT_VOICE}
    return {str(voice): str(recorded) for voice, recorded in reported.items()}


def _detail(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read().decode("utf-8")).get("detail", ""))
    except Exception:  # noqa: BLE001 - a body that is not our JSON
        return error.reason or ""


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """16-bit mono PCM WAV to float32 samples in [-1, 1]."""
    with wave.open(io.BytesIO(data), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise SynthesisError("the remote voice returned audio that is not 16-bit mono")
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767.0
    return pcm, rate
