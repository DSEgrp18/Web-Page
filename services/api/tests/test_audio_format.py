"""Ogg Opus audio: smaller, off by default, and always labelled for what it is."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile
from conftest import as_reader
from fastapi.testclient import TestClient
from test_api import _first_segment

from sinhala_reader import Deps, create_app
from sinhala_reader.audio import (
    AUDIO_FORMAT_ENV,
    SynthesisService,
    audio_format,
    encode,
    encode_wav,
)
from sinhala_reader.storage import InMemoryStore


def speech_like(seconds: float = 10.0, rate: int = 24_000) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    noise = np.random.default_rng(0).standard_normal(t.size)
    return 0.3 * np.sin(2 * np.pi * 180 * t) * (1 + np.sin(2 * np.pi * 3 * t)) + 0.05 * noise


class TestEncoding:
    def test_opus_is_about_24_kbps_and_decodes_to_the_same_length(self) -> None:
        samples = speech_like()

        data, media_type = encode(samples, 24_000, "opus")

        assert media_type == "audio/ogg" and data.startswith(b"OggS")
        assert 15 <= len(data) * 8 / 10 / 1000 <= 35  # kbps
        assert len(data) * 10 < len(encode_wav(samples, 24_000))
        decoded, rate = soundfile.read(io.BytesIO(data))
        assert abs(len(decoded) / rate - 10.0) < 0.1

    def test_a_rate_opus_cannot_take_stays_wav(self) -> None:
        data, media_type = encode(speech_like(1.0, 22_050), 22_050, "opus")

        assert media_type == "audio/wav" and data.startswith(b"RIFF")

    def test_wav_is_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(AUDIO_FORMAT_ENV, raising=False)

        assert audio_format() == "wav"

    def test_an_unknown_format_stops_the_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(AUDIO_FORMAT_ENV, "mp3")

        with pytest.raises(RuntimeError):
            audio_format()


def test_the_api_serves_opus_as_ogg(prepared_document, deps: Deps, client: TestClient) -> None:
    deps.synthesis = SynthesisService(deps.adapter, deps.store, encoding="opus")
    document_id = prepared_document["document_id"]
    segment = _first_segment(client, document_id)

    response = client.get(
        f"/documents/{document_id}/segments/{segment['segment_id']}/audio",
        headers=as_reader(client),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/ogg"
    assert response.content.startswith(b"OggS")
    assert ".ogg" in response.headers["content-disposition"]


def test_opus_is_named_among_the_limitations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUDIO_FORMAT_ENV, "opus")
    client = TestClient(create_app(Deps(store=InMemoryStore(), run_in_background=False)))

    notes = client.get("/readiness").json()

    assert "Opus" in str(notes)
