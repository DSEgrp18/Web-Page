"""Speech-region detection, exercised with constructed waveforms.

The shapes below are the ones measured in real output from this model: speech
then silence (correct), and speech, pause, more sound (the appended-audio
failure the user confirmed by listening).
"""

from __future__ import annotations

import numpy as np

from sinhala_tts.speech_regions import (
    find_speech_regions,
    frame_energy,
    trailing_audio_seconds,
    trim_to_first_utterance,
)

RATE = 24000


def tone(seconds: float, amplitude: float = 0.3) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(RATE * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def test_speech_followed_by_silence_is_one_region() -> None:
    """The shape of a correctly terminated utterance: plain-short-1.wav."""
    audio = np.concatenate([tone(1.26), silence(0.62)])
    regions = find_speech_regions(audio, RATE)
    assert len(regions) == 1
    assert regions[0].start_seconds == 0.0
    assert 1.2 <= regions[0].end_seconds <= 1.35
    assert trailing_audio_seconds(audio, RATE) == 0.0


def test_appended_audio_after_a_gap_is_detected() -> None:
    """The failure: plain-short-5.wav, sentence then 0.52s pause then 3.65s more."""
    audio = np.concatenate([tone(1.40), silence(0.52), tone(3.65)])
    regions = find_speech_regions(audio, RATE)
    assert len(regions) == 2
    trailing = trailing_audio_seconds(audio, RATE)
    assert 3.4 <= trailing <= 3.9, trailing


def test_short_pauses_inside_speech_do_not_split_it() -> None:
    """A 0.2s pause is a comma, not the end of an utterance.

    Measured internal pauses were 0.16-0.26s; splitting on those would report
    every comma as appended audio.
    """
    audio = np.concatenate([tone(0.8), silence(0.2), tone(0.8), silence(0.5)])
    assert len(find_speech_regions(audio, RATE)) == 1
    assert trailing_audio_seconds(audio, RATE) == 0.0


def test_leading_silence_is_excluded() -> None:
    audio = np.concatenate([silence(0.5), tone(1.0), silence(0.5)])
    regions = find_speech_regions(audio, RATE)
    assert len(regions) == 1
    assert 0.45 <= regions[0].start_seconds <= 0.55


def test_pure_silence_has_no_regions() -> None:
    assert find_speech_regions(silence(2.0), RATE) == []
    assert trailing_audio_seconds(silence(2.0), RATE) == 0.0


def test_empty_audio_is_handled() -> None:
    empty = np.array([], dtype=np.float32)
    assert find_speech_regions(empty, RATE) == []
    assert trailing_audio_seconds(empty, RATE) == 0.0


def test_quiet_speech_is_still_speech() -> None:
    """The threshold is relative to the clip's own peak, so a quiet but
    consistent clip must not read as silence throughout."""
    audio = np.concatenate([tone(1.0, amplitude=0.02), silence(0.5)])
    assert len(find_speech_regions(audio, RATE)) == 1


def test_a_brief_blip_is_not_a_region() -> None:
    """A 40ms tick after a long pause is not a second utterance."""
    audio = np.concatenate([tone(1.0), silence(0.5), tone(0.04), silence(0.2)])
    assert len(find_speech_regions(audio, RATE)) == 1


def test_frame_energy_tracks_amplitude() -> None:
    loud = frame_energy(tone(0.5, amplitude=0.5), RATE)
    quiet = frame_energy(tone(0.5, amplitude=0.05), RATE)
    assert loud.mean() > quiet.mean() * 5


def test_three_regions_measure_from_the_first_boundary() -> None:
    """plain-short-3.wav had the sentence then two further bursts.

    Trailing audio is everything after the first region ends, not just the last
    burst.
    """
    audio = np.concatenate([tone(1.36), silence(0.44), tone(0.7), silence(0.46), tone(0.97)])
    regions = find_speech_regions(audio, RATE)
    assert len(regions) == 3
    trailing = trailing_audio_seconds(audio, RATE)
    # 0.7s + 0.97s of appended sound, with the pauses between them excluded.
    assert 1.4 <= trailing <= 1.9, trailing


# --------------------------------------------------------------------------
# Trimming
# --------------------------------------------------------------------------


def test_trimming_leaves_clean_audio_untouched() -> None:
    """Safe to apply unconditionally: clean output must pass through."""
    audio = np.concatenate([tone(1.26), silence(0.62)])
    trimmed, removed = trim_to_first_utterance(audio, RATE)
    assert removed == 0.0
    assert len(trimmed) == len(audio)


def test_trimming_removes_appended_audio() -> None:
    audio = np.concatenate([tone(1.40), silence(0.52), tone(3.65)])
    trimmed, removed = trim_to_first_utterance(audio, RATE)
    assert removed > 3.5
    # The sentence plus padding survives; the appended sound does not.
    assert 1.4 <= len(trimmed) / RATE <= 1.7


def test_trimming_keeps_padding_after_the_last_word() -> None:
    """Cutting exactly at the energy boundary clips the final consonant."""
    audio = np.concatenate([tone(1.00), silence(0.50), tone(2.00)])
    trimmed, _ = trim_to_first_utterance(audio, RATE, tail_padding_ms=150)
    assert len(trimmed) / RATE > 1.10


def test_trimming_a_multi_sentence_clip_destroys_the_second_sentence() -> None:
    """Documenting the danger, not endorsing it.

    This is why the caller must guarantee one sentence per segment: the result
    sounds like a sentence that ended, not one that is missing.
    """
    two_sentences = np.concatenate([tone(1.5), silence(0.5), tone(1.5)])
    trimmed, removed = trim_to_first_utterance(two_sentences, RATE)
    assert removed > 1.4
    assert len(trimmed) / RATE < 2.0
