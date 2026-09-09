"""Audio sanity checks, exercised with synthetic waveforms.

These run in CI without the model, which is the point: the checks that decide
whether generated audio is servable must themselves be trustworthy, and waiting
for a GPU to find out that a threshold is inverted is too late.

Each failure mode below is one a listener would notice and an HTTP 200 would
not.
"""

from __future__ import annotations

import numpy as np
import pytest

from sinhala_tts.audio_checks import (
    EXPECTED_SAMPLE_RATE,
    MAX_UTTERANCE_SECONDS,
    check_audio,
)

RATE = EXPECTED_SAMPLE_RATE


def speech_like(seconds: float, amplitude: float = 0.3, rate: int = RATE) -> np.ndarray:
    """A tone at a speech-ish amplitude. Not speech, but it passes for one here."""
    t = np.linspace(0.0, seconds, int(rate * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_plausible_audio_passes() -> None:
    report = check_audio(speech_like(2.0), RATE, model_text="mama gedhara yanavaa.")
    assert report.ok, report.problems
    assert report.duration_seconds == pytest.approx(2.0, abs=0.01)
    assert report.sample_rate == RATE


def test_empty_output_is_reported() -> None:
    report = check_audio(np.array([], dtype=np.float32), RATE)
    assert not report.ok
    assert "no samples" in report.problems[0]


def test_silence_is_caught() -> None:
    """The failure this module exists for: a valid WAV containing nothing."""
    report = check_audio(np.zeros(RATE * 2, dtype=np.float32), RATE)
    assert not report.ok
    assert any("silent" in problem for problem in report.problems)


def test_near_silence_with_one_click_is_caught() -> None:
    """Peak alone would pass this: one loud sample, silence everywhere else."""
    samples = np.zeros(RATE * 2, dtype=np.float32)
    samples[1000] = 0.9
    report = check_audio(samples, RATE)
    assert not report.ok
    assert any("almost entirely silent" in problem for problem in report.problems)


def test_nan_is_caught_and_does_not_poison_the_measurements() -> None:
    samples = speech_like(1.0)
    samples[500] = np.nan
    samples[900] = np.inf
    report = check_audio(samples, RATE)
    assert not report.ok
    assert any("NaN or infinite" in problem for problem in report.problems)
    # Measurements must still be usable for diagnosis rather than all NaN.
    assert np.isfinite(report.peak)
    assert np.isfinite(report.rms)


def test_clipping_is_caught() -> None:
    samples = np.full(RATE, 1.0, dtype=np.float32)
    report = check_audio(samples, RATE)
    assert not report.ok
    assert any("clipped" in problem for problem in report.problems)


def test_occasional_overshoot_is_tolerated() -> None:
    """XTTS overshoots [-1, 1] now and then; a few samples are inaudible."""
    samples = speech_like(2.0)
    samples[:10] = 1.0
    report = check_audio(samples, RATE, model_text="mama gedhara yanavaa.")
    assert report.ok, report.problems


def test_wrong_sample_rate_is_caught() -> None:
    report = check_audio(speech_like(2.0, rate=22050), 22050, model_text="mama gedhara")
    assert not report.ok
    assert any("sample rate" in problem for problem in report.problems)


def test_audio_at_the_model_ceiling_is_flagged_as_truncated() -> None:
    """The model stops emitting at its audio-token limit rather than failing, so
    a clip at the ceiling was probably cut off mid-sentence."""
    report = check_audio(speech_like(MAX_UTTERANCE_SECONDS), RATE)
    assert not report.ok
    assert any("truncated" in problem for problem in report.problems)


def test_a_long_sentence_producing_a_fragment_is_caught() -> None:
    """Half a second of audio for a paragraph of text: speech went missing."""
    report = check_audio(speech_like(0.5), RATE, model_text="x" * 400)
    assert not report.ok
    assert any("characters per second" in problem for problem in report.problems)


def test_a_short_text_producing_minutes_of_audio_is_caught() -> None:
    """The model looping, which it does when conditioning goes wrong."""
    report = check_audio(speech_like(20.0), RATE, model_text="ada")
    assert not report.ok
    assert any("characters per second" in problem for problem in report.problems)


def test_speech_rate_is_not_checked_without_text() -> None:
    """Duration alone says nothing without knowing what was asked for."""
    report = check_audio(speech_like(3.0), RATE)
    assert report.ok, report.problems


def test_report_summary_is_readable() -> None:
    summary = check_audio(speech_like(1.0), RATE).summary()
    assert summary.startswith("OK:")
    assert "Hz" in summary
