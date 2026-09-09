"""The synthesis adapter, exercised through the development implementation.

These run in CI without torch, CUDA, or the checkpoint. That is the point of the
boundary: everything above the adapter can be built and tested on any machine,
and the parts that need a GPU are confined to one class.

The development adapter shares the real one's text validation, so a segment
rejected in production is rejected here too.
"""

from __future__ import annotations

import numpy as np
import pytest

from sinhala_tts.adapter import (
    DEFAULT_MODEL_DIR_ENV,
    DevelopmentAdapter,
    ReadinessState,
    SynthesisError,
    SynthesisSettings,
    TextNotSpeakableError,
    TextTooLongError,
    health,
    resolve_model_dir,
)

SENTENCE = "පිටුව 42 බලන්න."


@pytest.fixture
def adapter() -> DevelopmentAdapter:
    return DevelopmentAdapter()


# --------------------------------------------------------------------------
# The interface
# --------------------------------------------------------------------------


def test_synthesis_returns_audio_and_metadata(adapter: DevelopmentAdapter) -> None:
    result = adapter.synthesize(SENTENCE, "si-female")
    assert isinstance(result.samples, np.ndarray)
    assert result.sample_rate == 24000
    assert result.metadata.duration_seconds > 0


def test_the_normalised_text_is_recorded_with_the_audio(adapter: DevelopmentAdapter) -> None:
    """Both stages are kept: the readable Sinhala and what the model was given.

    Without the spoken text a pronunciation complaint cannot be diagnosed, and
    without the model text the cache key cannot be reproduced.
    """
    result = adapter.synthesize(SENTENCE, "si-female")
    assert result.metadata.spoken_text == "පිටුව හතළිස් දෙක බලන්න."
    assert result.metadata.model_text == "pituva hathalis dheka balanna."


def test_every_segment_records_what_produced_it(adapter: DevelopmentAdapter) -> None:
    """CLAUDE.md requires model version and settings on every generated segment."""
    result = adapter.synthesize(SENTENCE, "si-female")
    meta = result.metadata
    assert meta.model_version
    assert meta.normalizer_version
    assert meta.settings.language == "en"
    assert meta.generated_at
    assert meta.readiness is ReadinessState.READY


# --------------------------------------------------------------------------
# The development adapter must never pass for the model
# --------------------------------------------------------------------------


def test_development_output_is_marked_as_not_real(adapter: DevelopmentAdapter) -> None:
    result = adapter.synthesize(SENTENCE, "si-female")
    assert result.metadata.is_real_model is False
    assert result.metadata.voice_id.startswith("development-")


def test_development_audio_cannot_share_a_cache_key_with_real_audio(
    adapter: DevelopmentAdapter,
) -> None:
    """Otherwise a placeholder tone could be served as narration from cache."""
    from dataclasses import replace

    development = adapter.synthesize(SENTENCE, "si-female").metadata
    pretend_real = replace(development, is_real_model=True)
    assert development.cache_key() != pretend_real.cache_key()


# --------------------------------------------------------------------------
# Cache identity
# --------------------------------------------------------------------------


def test_cache_key_is_stable_for_identical_inputs(adapter: DevelopmentAdapter) -> None:
    first = adapter.synthesize(SENTENCE, "si-female").metadata.cache_key()
    second = adapter.synthesize(SENTENCE, "si-female").metadata.cache_key()
    assert first == second


def test_cache_key_changes_with_the_text(adapter: DevelopmentAdapter) -> None:
    a = adapter.synthesize(SENTENCE, "si-female").metadata.cache_key()
    b = adapter.synthesize("පිටුව 43 බලන්න.", "si-female").metadata.cache_key()
    assert a != b


def test_cache_key_changes_with_generation_settings(adapter: DevelopmentAdapter) -> None:
    a = adapter.synthesize(SENTENCE, "si-female").metadata.cache_key()
    b = adapter.synthesize(
        SENTENCE, "si-female", SynthesisSettings(temperature=0.30)
    ).metadata.cache_key()
    assert a != b


def test_cache_key_changes_with_the_normalizer_version(adapter: DevelopmentAdapter) -> None:
    """A change to how numbers are written out changes the speech.

    Serving the old audio afterwards would be a silent regression, so the
    normalizer version has to be part of cache identity.
    """
    from dataclasses import replace

    meta = adapter.synthesize(SENTENCE, "si-female").metadata
    assert meta.cache_key() != replace(meta, normalizer_version="99").cache_key()


def test_cache_key_changes_with_the_document_version(adapter: DevelopmentAdapter) -> None:
    """A correction creates a new document version and must invalidate audio."""
    a = adapter.synthesize(SENTENCE, "si-female", document_version="v1").metadata
    b = adapter.synthesize(SENTENCE, "si-female", document_version="v2").metadata
    assert a.cache_key() != b.cache_key()


def test_settings_fingerprint_distinguishes_every_field() -> None:
    base = SynthesisSettings()
    from dataclasses import fields, replace

    for f in fields(base):
        current = getattr(base, f.name)
        changed = (
            not current
            if isinstance(current, bool)
            else (current + 1 if isinstance(current, int | float) else current + "x")
        )
        assert replace(base, **{f.name: changed}).fingerprint() != base.fingerprint(), f.name


# --------------------------------------------------------------------------
# Text guards, shared with the real adapter
# --------------------------------------------------------------------------


def test_unspeakable_text_is_refused(adapter: DevelopmentAdapter) -> None:
    """Synthesising it would cache a silent clip as valid audio."""
    with pytest.raises(TextNotSpeakableError):
        adapter.synthesize("()[]{}#@", "si-female")


def test_empty_text_is_refused(adapter: DevelopmentAdapter) -> None:
    with pytest.raises(TextNotSpeakableError):
        adapter.synthesize("   ", "si-female")


def test_oversized_text_is_refused_rather_than_truncated(adapter: DevelopmentAdapter) -> None:
    """Nothing splits text for us; the model would warn and produce clipped audio."""
    with pytest.raises(TextTooLongError) as error:
        adapter.synthesize("මම ගෙදර යනවා. " * 40, "si-female")
    assert "Segment the text" in str(error.value)


# --------------------------------------------------------------------------
# Readiness, liveness, and configuration
# --------------------------------------------------------------------------


def test_health_reports_development_output_as_a_placeholder(
    adapter: DevelopmentAdapter,
) -> None:
    report = health(adapter)
    assert report.alive
    assert report.serving
    assert any("placeholder tone" in note for note in report.notes)


def test_missing_model_configuration_fails_with_an_actionable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DEFAULT_MODEL_DIR_ENV, raising=False)
    with pytest.raises(SynthesisError) as error:
        resolve_model_dir()
    assert DEFAULT_MODEL_DIR_ENV in str(error.value)


def test_incomplete_bundle_names_what_is_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial bundle must fail here, not deep inside the loader."""
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(DEFAULT_MODEL_DIR_ENV, str(tmp_path))
    with pytest.raises(SynthesisError) as error:
        resolve_model_dir()
    message = str(error.value)
    assert "model.pth" in message
    assert "vocab.json" in message
    assert "reference.wav" in message


def test_readiness_states_are_distinct() -> None:
    """Liveness, readiness, and degraded performance are three different things."""
    assert ReadinessState.READY is not ReadinessState.DEGRADED
    assert ReadinessState.NOT_LOADED is not ReadinessState.FAILED


# --------------------------------------------------------------------------
# The placeholder still behaves plausibly
# --------------------------------------------------------------------------


def test_placeholder_duration_follows_the_measured_model(adapter: DevelopmentAdapter) -> None:
    """Timing-dependent code above the adapter should see something realistic."""
    short = adapter.synthesize("මම ගෙදර යනවා.", "si-female")
    longer = adapter.synthesize("අද දවසේ කාලගුණය ඉතා හොඳයි. අපි උදෑසන පාසල් ගියෙමු.", "si-female")
    assert longer.metadata.duration_seconds > short.metadata.duration_seconds


def test_placeholder_audio_passes_the_audio_checks(adapter: DevelopmentAdapter) -> None:
    """It is a tone, but it must not look broken to the checks downstream."""
    result = adapter.synthesize(SENTENCE, "si-female")
    assert result.metadata.audio_report is not None
    assert result.metadata.audio_report.ok, result.metadata.audio_report.problems


# --------------------------------------------------------------------------
# Knowing the cache key before generating anything
# --------------------------------------------------------------------------


def test_the_predicted_cache_key_is_the_one_synthesis_produces(
    adapter: DevelopmentAdapter,
) -> None:
    """Caching is worthless if finding out whether audio exists costs a synthesis.

    There is one implementation of the key, and both paths go through it. If
    these ever diverge, every cache lookup misses and every segment is generated
    again — silently, and only visible as a GPU bill.
    """
    predicted = adapter.cache_key(SENTENCE, "si-female", document_version="v1")
    actual = adapter.synthesize(SENTENCE, "si-female", document_version="v1").metadata.cache_key()
    assert predicted == actual


def test_the_predicted_key_changes_with_everything_the_real_one_does(
    adapter: DevelopmentAdapter,
) -> None:
    base = adapter.cache_key(SENTENCE, "si-female", document_version="v1")
    assert base != adapter.cache_key("පිටුව 43 බලන්න.", "si-female", document_version="v1")
    assert base != adapter.cache_key(SENTENCE, "si-male", document_version="v1")
    assert base != adapter.cache_key(SENTENCE, "si-female", document_version="v2")
    assert base != adapter.cache_key(
        SENTENCE, "si-female", SynthesisSettings(temperature=0.3), document_version="v1"
    )


def test_predicting_a_key_applies_the_same_text_guards(adapter: DevelopmentAdapter) -> None:
    """An unspeakable segment is refused at lookup, not at generation."""
    with pytest.raises(TextNotSpeakableError):
        adapter.cache_key("()[]{}", "si-female")


def test_an_adapter_says_whether_it_is_the_real_model(adapter: DevelopmentAdapter) -> None:
    """Callers need this without synthesising, to label audio and key the cache."""
    assert adapter.is_real_model is False
    assert adapter.model_version == "development-adapter"


def test_the_recorded_voice_id_is_not_the_one_that_was_asked_for(
    adapter: DevelopmentAdapter,
) -> None:
    """The prefix has to reach the cache key, not just the response.

    Otherwise a placeholder generated today would share a key with real
    narration generated later.
    """
    assert adapter.voice_id_for("si-female") == "development-si-female"
    result = adapter.synthesize(SENTENCE, "si-female")
    assert result.metadata.voice_id == "development-si-female"
