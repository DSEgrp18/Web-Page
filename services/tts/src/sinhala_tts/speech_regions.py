"""Find where speech starts and stops inside generated audio.

Why this exists
---------------
This model appends invented sound after the end of a sentence, sometimes. It was
found by synthesising ``මම ගෙදර යනවා.`` six times with identical input and
settings and getting durations of 1.90, 2.27, 4.45, 4.31, 5.57 and 2.55 seconds,
then listening: the long ones contain the sentence followed by extra sound.

Measuring the waveform showed the structure clearly. The sentence itself ends
between 1.00 s and 1.44 s in **every** clip. What varies is whether the model
then stops, or carries on after a pause:

===============  =================  ==========  ======================
Clip             Sentence ends      Gap         Audio after the gap
===============  =================  ==========  ======================
1.90 s            1.26 s            0.62 s      none
2.27 s            1.44 s            0.62 s      none
4.45 s            1.36 s            0.44 s      2.65 s
4.31 s            1.44 s            0.70 s      2.17 s
5.57 s            1.40 s            0.52 s      3.65 s
===============  =================  ==========  ======================

So the appended material is separated from the real speech by a silence, which
makes it detectable.

.. warning::

   **This module detects. It does not trim.**

   Cutting audio automatically would risk truncating real speech, and for a
   reader used by people who cannot see the page, silently dropping the end of a
   sentence is far worse than a stretch of unwanted sound. A listener can tell
   that trailing noise is not part of the book. They cannot tell that a sentence
   was cut short.

   The known false positive is a sentence containing a long pause of its own —
   at a comma, a colon, or between two sentences sent as one segment. Measured
   internal pauses in these samples were 0.16-0.26 s and the pauses before
   appended material were 0.26-0.70 s, so the two ranges **overlap**. A
   threshold cannot separate them reliably, which is precisely why this reports
   for review instead of acting.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Analysis window. Short enough to locate a boundary usefully, long enough that
# a single quiet sample does not read as a pause.
FRAME_MS = 20

# A frame counts as silent below this fraction of the clip's own peak.
# Generated audio has a noise floor, so an absolute threshold does not travel
# between clips.
SILENCE_RATIO = 0.02

# ...but a clip that is entirely near-silent would otherwise have its own noise
# floor treated as speech, so the relative threshold has an absolute lower bound.
SILENCE_FLOOR = 0.005

# A pause must be at least this long to be treated as a boundary. Chosen from
# the measurements above: it clears the 0.16-0.26 s pauses seen inside speech
# while catching the 0.44-0.70 s pauses that preceded appended material.
#
# It does NOT clear all of them — one sample showed a 0.26 s pause before
# appended sound. Provisional, and the reason this reports rather than trims.
MIN_SILENCE_MS = 350

# Speech shorter than this either side of a gap is a blip, not an utterance.
MIN_REGION_MS = 120


@dataclass(frozen=True)
class SpeechRegion:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def frame_energy(samples: np.ndarray, sample_rate: int, frame_ms: int = FRAME_MS) -> np.ndarray:
    """Root-mean-square per frame."""
    frame = max(1, sample_rate * frame_ms // 1000)
    count = len(samples) // frame
    if count == 0:
        return np.zeros(0, dtype=np.float64)
    frames = np.asarray(samples, dtype=np.float64)[: count * frame].reshape(count, frame)
    return np.sqrt(np.mean(np.square(frames), axis=1))


def find_speech_regions(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_ms: int = FRAME_MS,
    silence_ratio: float = SILENCE_RATIO,
    min_silence_ms: int = MIN_SILENCE_MS,
    min_region_ms: int = MIN_REGION_MS,
) -> list[SpeechRegion]:
    """Contiguous stretches of sound, split at pauses of at least the threshold.

    Leading and trailing silence are excluded, so a clip that is speech followed
    by silence yields exactly one region ending where the speech ends.
    """
    samples = np.asarray(samples, dtype=np.float64).reshape(-1)
    if samples.size == 0:
        return []

    energy = frame_energy(samples, sample_rate, frame_ms)
    if energy.size == 0:
        return []

    peak = float(np.max(np.abs(samples)))
    threshold = max(silence_ratio * peak, SILENCE_FLOOR)
    loud = energy >= threshold
    if not loud.any():
        return []

    min_silence_frames = max(1, min_silence_ms // frame_ms)
    seconds_per_frame = frame_ms / 1000.0

    regions: list[tuple[int, int]] = []
    start = None
    silence_run = 0
    for index, is_loud in enumerate(loud):
        if is_loud:
            if start is None:
                start = index
            silence_run = 0
            end = index + 1
        else:
            if start is not None:
                silence_run += 1
                if silence_run >= min_silence_frames:
                    regions.append((start, end))
                    start = None
                    silence_run = 0
    if start is not None:
        regions.append((start, end))

    min_region_frames = max(1, min_region_ms // frame_ms)
    return [
        SpeechRegion(
            start_seconds=first * seconds_per_frame,
            end_seconds=last * seconds_per_frame,
        )
        for first, last in regions
        if last - first >= min_region_frames
    ]


def trailing_audio_seconds(
    samples: np.ndarray,
    sample_rate: int,
    **kwargs: object,
) -> float:
    """Seconds of *sound* after the first speech region, excluding the pauses.

    Summed across every later region rather than measured end-to-end, so the
    figure is how much extra audio a listener would hear, not how long the clip
    ran on for. The pause itself is not the problem; the sound after it is.

    Zero when the clip holds one region followed only by silence, which is what
    a correctly terminated utterance looks like.

    Only meaningful when the input was a **single** sentence. For a segment
    holding two sentences this measures the second one, which is not a fault.
    """
    regions = find_speech_regions(samples, sample_rate, **kwargs)  # type: ignore[arg-type]
    if len(regions) < 2:
        return 0.0
    return sum(region.duration_seconds for region in regions[1:])
