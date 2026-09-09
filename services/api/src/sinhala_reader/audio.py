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
import threading
import wave

import numpy as np
from sinhala_tts.adapter import SynthesisSettings, TtsAdapter

from .storage import AudioRecord, Store

#: 16-bit PCM. The reader plays it in a browser, and 16-bit is what every
#: browser decodes without a codec; the model's float output is louder than the
#: format allows only if it clips, which the audio checks already look for.
_SAMPLE_WIDTH = 2


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

    def __init__(self, adapter: TtsAdapter, store: Store, voice_id: str = "si-female") -> None:
        self._adapter = adapter
        self._store = store
        self._voice_id = voice_id
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def adapter(self) -> TtsAdapter:
        return self._adapter

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def cache_key_for(
        self, text: str, document_version: str, settings: SynthesisSettings | None = None
    ) -> str:
        """The key this text would be cached under, without generating anything.

        Lets a caller check the cache before taking a synthesis lock, which is
        what makes the common case — audio already generated — cost nothing.
        """
        return self._adapter.cache_key(
            text, self._voice_id, settings, document_version=document_version
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
    ) -> AudioRecord:
        """Return cached audio for this segment, generating it if needed."""
        key = self.cache_key_for(text, document_version, settings)

        cached = self._store.get_audio(key, owner)
        if cached is not None:
            return cached

        with self._lock_for(key):
            # Another caller may have finished while this one waited.
            cached = self._store.get_audio(key, owner)
            if cached is not None:
                return cached

            result = self._adapter.synthesize(
                text, self._voice_id, settings, document_version=document_version
            )
            record = AudioRecord(
                cache_key=result.metadata.cache_key(),
                document_id=document_id,
                owner=owner,
                segment_id=segment_id,
                wav=encode_wav(result.samples, result.sample_rate),
                duration_seconds=result.metadata.duration_seconds,
                is_real_model=result.metadata.is_real_model,
                voice_id=result.metadata.voice_id,
                model_version=result.metadata.model_version,
            )
            return self._store.put_audio(record)
