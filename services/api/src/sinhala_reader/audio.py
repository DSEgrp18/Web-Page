"""Generating, encoding and caching segment audio.

Three things this is careful about, each because getting it wrong is invisible
to the person listening:

* **A placeholder is never served as narration.** The development adapter
  produces a tone. Its output carries ``is_real_model=False`` all the way to the
  HTTP response, and the flag is part of the cache key, so a tone generated
  today cannot be handed out as speech once a real model exists.
* **The same segment is never generated twice at once.** Prefetch and playback
  ask for the same audio constantly. Without deduplication the second caller
  starts a second GPU job for a result the first is already producing —
  CLAUDE.md calls this out specifically.
* **Cache identity includes everything that changes the sound.** The adapter
  builds the key from text, document version, model version, normaliser version,
  voice and settings; nothing here shortens it.
"""

from __future__ import annotations

import io
import os
import threading
import wave

import numpy as np
from sinhala_tts.adapter import SynthesisSettings, TtsAdapter

from .storage import AudioRecord, Store

#: 16-bit PCM. The reader plays it in a browser, and 16-bit is what every
#: browser decodes without a codec; the model's float output is louder than the
#: format allows only if it clips, which the audio checks already look for.
_SAMPLE_WIDTH = 2


#: ``wav`` (the default) or ``opus``. Opus is about 24 kbps, some 11 MB an hour
#: against WAV's 173 MB, which is what makes downloading a chapter to a cheap
#: phone reasonable. It stays off until a blind listening comparison (RQ4 in
#: docs/product-plan.md) shows it costs the voice nothing a listener can hear.
AUDIO_FORMAT_ENV = "SINHALA_READER_AUDIO_FORMAT"
AUDIO_FORMATS = ("wav", "opus")

#: libsndfile's Opus bitrate falls linearly from about 256 kbps at level 0 to
#: about 6 kbps at level 1; 0.93 is about 24 kbps, measured.
_OPUS_LEVEL = 0.93

#: The sample rates Opus encodes. Anything else stays WAV rather than being
#: resampled here, where nobody would hear what resampling did.
_OPUS_RATES = {8_000, 12_000, 16_000, 24_000, 48_000}


def audio_format() -> str:
    """The configured format. Fatal on anything unknown, never a silent default."""
    value = os.environ.get(AUDIO_FORMAT_ENV, "wav").strip().lower() or "wav"
    if value not in AUDIO_FORMATS:
        raise RuntimeError(f"{AUDIO_FORMAT_ENV}={value!r}: expected one of {AUDIO_FORMATS}.")
    return value


def extension_for(media_type: str) -> str:
    return "ogg" if media_type == "audio/ogg" else "wav"


def encode_opus(samples: np.ndarray, sample_rate: int) -> bytes:
    """Float samples to Ogg Opus, mono, about 24 kbps. Clipped, as WAV is."""
    import soundfile  # only where Opus is chosen: the voice images carry it

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    buffer = io.BytesIO()
    soundfile.write(
        buffer,
        clipped,
        sample_rate,
        format="OGG",
        subtype="OPUS",
        compression_level=_OPUS_LEVEL,
    )
    return buffer.getvalue()


def encode(samples: np.ndarray, sample_rate: int, fmt: str) -> tuple[bytes, str]:
    """Encoded audio and its media type, in ``fmt`` where that can be done."""
    if fmt == "opus" and sample_rate in _OPUS_RATES:
        return encode_opus(samples, sample_rate), "audio/ogg"
    return encode_wav(samples, sample_rate), "audio/wav"


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Float samples to a WAV file.

    Clipped rather than normalised. Normalising would quietly rescale a clip
    that came out too loud, hiding a generation fault the audio checks exist to
    catch; clipping leaves the fault audible and detectable.
    """
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(_SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


class SynthesisService:
    """Turns a segment into cached, owner-scoped audio.

    In-flight deduplication is per cache key: the first caller synthesises while
    the others wait on the same lock and then find the finished result in the
    store. It is deliberately simple — one lock per key, held for the duration —
    because the alternative is a future map that has to be reasoned about under
    failure, and this service will move behind a real job queue before that
    complexity would pay for itself.
    """

    def __init__(
        self,
        adapter: TtsAdapter,
        store: Store,
        voice_id: str = "si-female",
        encoding: str | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._voice_id = voice_id
        self._format = encoding or audio_format()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def adapter(self) -> TtsAdapter:
        return self._adapter

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def cache_key_for(
        self,
        text: str,
        document_version: str,
        settings: SynthesisSettings | None = None,
        *,
        prepared: tuple[str, str] | None = None,
    ) -> str:
        """The key this text would be cached under, without generating anything.

        Lets a caller check the cache before taking a synthesis lock, which is
        what makes the common case — audio already generated — cost nothing.

        ``prepared`` is the segment's stored ``(spoken_text, model_text)``. Pass
        it wherever the segment is known: the key must be derived from the same
        text the synthesis will speak, or a lookup misses audio that exists.
        """
        return self._adapter.cache_key(
            text, self._voice_id, settings, document_version=document_version, prepared=prepared
        )

    def synthesize(
        self,
        *,
        text: str,
        document_id: str,
        owner: str,
        segment_id: str,
        document_version: str,
        settings: SynthesisSettings | None = None,
        prepared: tuple[str, str] | None = None,
    ) -> AudioRecord:
        """Return cached audio for this segment, generating it if needed."""
        key = self.cache_key_for(text, document_version, settings, prepared=prepared)

        cached = self._store.get_audio(key, document_id, owner)
        if cached is not None:
            return cached

        with self._lock_for(key):
            # Another caller may have finished while this one waited.
            cached = self._store.get_audio(key, document_id, owner)
            if cached is not None:
                return cached

            result = self._adapter.synthesize(
                text,
                self._voice_id,
                settings,
                document_version=document_version,
                prepared=prepared,
            )
            encoded, media_type = encode(result.samples, result.sample_rate, self._format)
            record = AudioRecord(
                cache_key=result.metadata.cache_key(),
                document_id=document_id,
                owner=owner,
                segment_id=segment_id,
                wav=encoded,
                media_type=media_type,
                duration_seconds=result.metadata.duration_seconds,
                is_real_model=result.metadata.is_real_model,
                voice_id=result.metadata.voice_id,
                model_version=result.metadata.model_version,
            )
            return self._store.put_audio(record)
