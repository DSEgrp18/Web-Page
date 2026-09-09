"""Sanity checks on generated audio.

A correctly formed WAV file can contain pure silence, a burst of clipping, or
NaN. None of those are visible from the file header, the HTTP status, or the
byte count, so "synthesis returned successfully" is not evidence that anything
audible was produced. CLAUDE.md requires decoded samples to be inspected for
finite values, non-silence, clipping, sample rate, and plausible duration, and
requires empty or suspiciously short or long output to be routed for review
rather than served.

These checks exist to catch the failures a listener would notice and a status
code would not: a sentence that narrates as silence, a segment truncated
mid-word by the model's audio-token ceiling, or a cache quietly storing either
of those as valid audio.

.. important::

   **The thresholds here are provisional and uncalibrated.** They were chosen to
   catch obvious failures, not tuned against ground truth. CLAUDE.md is explicit
   that numerical thresholds from elsewhere must not be adopted as proven
   defaults, and the same applies to these. Calibrate them once there is a body
   of real generated audio and human listening judgements to calibrate against.

   Treat a failure as "route this for review", not as a measurement of quality.
   These checks cannot tell you whether the speech is intelligible, correctly
   pronounced, or in the right language. Only listening can.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .speech_regions import find_speech_regions, trailing_audio_seconds

# The model's output rate, from config.json model_args.output_sample_rate.
EXPECTED_SAMPLE_RATE = 24000

# Derived ceiling on a single generation: gpt_max_audio_tokens (605) ×
# gpt_code_stride_len (1024) ÷ output_sample_rate (24000) ≈ 25.81 s. Audio at or
# near this length was probably cut off rather than finished, because the model
# stops emitting rather than failing. Derived from the config, not measured.
MAX_UTTERANCE_SECONDS = 605 * 1024 / EXPECTED_SAMPLE_RATE

# Within this margin of the ceiling, assume truncation rather than a sentence
# that happened to end exactly there.
TRUNCATION_MARGIN_SECONDS = 0.3

# Peak amplitude below this is silence for practical purposes: a 16-bit sample
# of 1 is about 3e-5, so this is a handful of least-significant bits.
SILENCE_PEAK = 1e-4

# Root-mean-square below this is effectively silence. A clip can hold a single
# loud click and still be silent everywhere else, which the peak test alone
# misses entirely.
#
# 5e-3 is about -46 dBFS. Speech from this model sits far above that, so the
# margin is wide; the value exists to separate "a tick and nothing else" from
# "quiet speech", not to judge loudness. Provisional, like every threshold here.
NEAR_SILENCE_RMS = 5e-3

# XTTS overshoots [-1, 1] occasionally and the writer clips it, which is
# inaudible for a few samples and a harsh buzz for many. Provisional.
CLIPPING_LEVEL = 0.999
MAX_CLIPPED_FRACTION = 0.01

# Speech-rate sanity, in characters of model input per second. Deliberately
# wide: it is meant to catch "one word of audio for a whole paragraph" and
# "ninety seconds for three words", not to judge pacing. Uncalibrated.
MIN_CHARS_PER_SECOND = 2.0
MAX_CHARS_PER_SECOND = 45.0

# Below this, no audio worth serving was produced regardless of the text.
MIN_DURATION_SECONDS = 0.15


# Appended sound beyond this is worth a human ear. Below it, a short burst after
# a pause is as likely to be breath or a natural sentence-final sound.
# Provisional, like everything else here.
MAX_TRAILING_SECONDS = 0.3


@dataclass(frozen=True)
class AudioReport:
    """What was measured, and what looks wrong.

    Carries the measurements as well as the verdict so a failure can be
    diagnosed and logged without regenerating the audio.
    """

    sample_rate: int
    sample_count: int
    duration_seconds: float
    peak: float
    rms: float
    clipped_fraction: float
    trailing_audio_seconds: float = 0.0
    speech_regions: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        verdict = "OK" if self.ok else "PROBLEMS"
        return (
            f"{verdict}: {self.duration_seconds:.2f}s @ {self.sample_rate} Hz, "
            f"peak {self.peak:.3f}, rms {self.rms:.4f}, "
            f"clipped {self.clipped_fraction * 100:.2f}%"
        )


def check_audio(
    samples: np.ndarray,
    sample_rate: int,
    *,
    model_text: str | None = None,
    expected_sample_rate: int = EXPECTED_SAMPLE_RATE,
    expect_single_utterance: bool = False,
) -> AudioReport:
    """Inspect decoded samples and report anything that looks wrong.

    ``samples`` is the float waveform as the model returns it, before any WAV
    encoding. ``model_text`` is the ASCII actually given to the model; when
    supplied, it enables the speech-rate check.

    Set ``expect_single_utterance`` when the text was one sentence. This model
    sometimes keeps generating after a sentence ends — confirmed by listening,
    and measured in ``speech_regions`` — and this reports it. Leave it off for
    text holding more than one sentence, where a second stretch of speech is
    correct and flagging it would be a false positive.

    Never raises for bad audio — it returns a report. Deciding what to do with a
    problem (retry, route for review, refuse to cache) belongs to the caller.
    """
    problems: list[str] = []

    samples = np.asarray(samples, dtype=np.float64).reshape(-1)
    sample_count = int(samples.size)

    if sample_count == 0:
        return AudioReport(
            sample_rate=sample_rate,
            sample_count=0,
            duration_seconds=0.0,
            peak=0.0,
            rms=0.0,
            clipped_fraction=0.0,
            trailing_audio_seconds=0.0,
            speech_regions=0,
            problems=["no samples were produced"],
        )

    # Finiteness first: NaN propagates through max and mean and would make every
    # measurement below meaningless.
    finite = np.isfinite(samples)
    if not finite.all():
        bad = int((~finite).sum())
        problems.append(f"{bad} of {sample_count} samples are NaN or infinite")
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)

    peak = float(np.max(np.abs(samples)))
    rms = float(math.sqrt(float(np.mean(np.square(samples)))))
    clipped_fraction = float(np.mean(np.abs(samples) >= CLIPPING_LEVEL))
    duration = sample_count / sample_rate if sample_rate else 0.0

    if sample_rate != expected_sample_rate:
        problems.append(f"sample rate is {sample_rate}, expected {expected_sample_rate}")

    if peak < SILENCE_PEAK:
        problems.append(f"audio is silent (peak {peak:.2e})")
    elif rms < NEAR_SILENCE_RMS:
        # Reported separately: a clip can pass the peak test on one click and
        # still be silence everywhere else.
        problems.append(f"audio is almost entirely silent (rms {rms:.2e})")

    if clipped_fraction > MAX_CLIPPED_FRACTION:
        problems.append(f"{clipped_fraction * 100:.1f}% of samples are clipped")

    if duration < MIN_DURATION_SECONDS:
        problems.append(f"audio is only {duration:.3f}s long")

    if duration >= MAX_UTTERANCE_SECONDS - TRUNCATION_MARGIN_SECONDS:
        problems.append(
            f"audio is {duration:.2f}s, at the model's {MAX_UTTERANCE_SECONDS:.2f}s "
            "ceiling and probably truncated mid-sentence"
        )

    if model_text:
        characters = len(model_text.strip())
        if characters and duration > 0:
            rate = characters / duration
            if rate < MIN_CHARS_PER_SECOND:
                problems.append(
                    f"only {rate:.1f} characters per second: "
                    f"{characters} characters took {duration:.2f}s"
                )
            elif rate > MAX_CHARS_PER_SECOND:
                problems.append(
                    f"{rate:.1f} characters per second: "
                    f"{characters} characters in only {duration:.2f}s, "
                    "so speech is probably missing"
                )

    trailing = trailing_audio_seconds(samples, sample_rate) if sample_rate else 0.0
    regions = len(find_speech_regions(samples, sample_rate)) if sample_rate else 0

    if expect_single_utterance and trailing > MAX_TRAILING_SECONDS:
        problems.append(
            f"{trailing:.2f}s of sound after the sentence ended, across "
            f"{regions} speech regions: the model probably kept generating"
        )

    return AudioReport(
        sample_rate=sample_rate,
        sample_count=sample_count,
        duration_seconds=duration,
        peak=peak,
        rms=rms,
        clipped_fraction=clipped_fraction,
        trailing_audio_seconds=trailing,
        speech_regions=regions,
        problems=problems,
    )
