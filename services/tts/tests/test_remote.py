"""The remote voice adapter, against a stand-in for the Modal endpoint.

The stand-in is a real HTTP server on the loopback address, so the request the
adapter builds and the bytes it decodes are the real ones; only the model is
replaced, by a sine wave.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import numpy as np
import pytest

from sinhala_tts.adapter import (
    ReadinessState,
    SynthesisError,
    TextNotSpeakableError,
    TextTooLongError,
)
from sinhala_tts.normalize import NORMALIZER_VERSION
from sinhala_tts.remote import RemoteVoiceAdapter

KEY = "test-key"


def _wav(seconds: float = 1.0, rate: int = 24000) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    pcm = (0.3 * np.sin(2 * np.pi * 180 * t) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


class FakeVoice:
    """Records every request; answers as the Modal endpoint does."""

    def __init__(self) -> None:
        self.requests: list[tuple[dict[str, Any], str | None]] = []
        self.normalizer = NORMALIZER_VERSION
        self.error: tuple[int, str] | None = None

    def answer(self, body: dict[str, Any], auth: str | None) -> tuple[int, dict[str, Any]]:
        self.requests.append((body, auth))
        if auth != f"Bearer {KEY}":
            return 401, {"detail": "missing or wrong key"}
        if self.error:
            return self.error[0], {"detail": self.error[1]}
        if body.get("status"):
            return 200, {
                "readiness": "ready",
                "model_version": "remote-v1",
                "device": "cuda (A10G, fp32)",
                "normalizer_version": self.normalizer,
            }
        return 200, {
            "wav": base64.b64encode(_wav()).decode("ascii"),
            "model_version": "remote-v1",
            "generate_seconds": 0.4,
        }


@pytest.fixture
def voice():
    fake = FakeVoice()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            code, payload = fake.answer(body, self.headers.get("Authorization"))
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_port}/"  # type: ignore[attr-defined]
    yield fake
    server.shutdown()


def adapter_for(voice: FakeVoice, key: str = KEY) -> RemoteVoiceAdapter:
    return RemoteVoiceAdapter(voice.url, key)  # type: ignore[attr-defined]


def test_load_takes_readiness_and_version_from_the_remote(voice):
    adapter = adapter_for(voice)
    assert adapter.readiness is ReadinessState.NOT_LOADED
    adapter.load()
    assert adapter.readiness is ReadinessState.READY
    assert adapter.model_version == "remote-v1"
    assert adapter.is_real_model
    assert voice.requests == [({"status": True}, f"Bearer {KEY}")]


def test_synthesize_sends_the_prepared_text_and_checks_what_comes_back(voice):
    adapter = adapter_for(voice)
    prepared = ("එක දශම එක", "eka dashama eka")
    result = adapter.synthesize("1.1", "si-female", document_version="v7", prepared=prepared)

    body, auth = voice.requests[-1]
    assert auth == f"Bearer {KEY}"
    assert body["prepared"] == list(prepared)
    assert body["document_version"] == "v7"
    assert body["settings"]["language"] == "en"

    assert result.sample_rate == 24000
    assert result.metadata.duration_seconds == pytest.approx(1.0, abs=0.01)
    assert result.metadata.model_version == "remote-v1"
    assert result.metadata.device == "cuda (A10G, fp32)"
    assert result.metadata.audio_report is not None
    # The key computed before synthesis describes the audio that came back.
    assert result.metadata.cache_key() == adapter.cache_key(
        "1.1", "si-female", document_version="v7", prepared=prepared
    )


def test_unspeakable_text_is_refused_before_any_request(voice):
    adapter = adapter_for(voice)
    with pytest.raises(TextNotSpeakableError):
        adapter.synthesize("...", "si-female")
    assert voice.requests == []


def test_a_wrong_key_says_which_setting_to_check(voice):
    with pytest.raises(SynthesisError, match="SINHALA_READER_TTS_KEY"):
        adapter_for(voice, key="wrong").load()


def test_the_remotes_text_errors_keep_their_type(voice):
    adapter = adapter_for(voice)
    adapter.load()
    voice.error = (422, "TextTooLongError: too long")
    with pytest.raises(TextTooLongError):
        adapter.synthesize("ශාක සෛලය", "si-female")


def test_a_different_normaliser_is_a_failed_load_not_a_silent_mismatch(voice):
    voice.normalizer = "different"
    adapter = adapter_for(voice)
    with pytest.raises(SynthesisError):
        adapter.load()
    assert adapter.readiness is ReadinessState.FAILED
    assert "normalises text" in (adapter.failure_reason or "")


def test_only_https_or_loopback():
    with pytest.raises(ValueError):
        RemoteVoiceAdapter("http://voice.example.org/", KEY)
    with pytest.raises(ValueError):
        RemoteVoiceAdapter("https://voice.example.org/", "")
