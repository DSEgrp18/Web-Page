"""The Gemini adapter, without a network.

Its contract is narrow and worth pinning: every way of failing to get an answer
is StructureUnavailable, and a wrong answer is never one - that is returned, so
that verification rejects it and somebody is told.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from sinhala_documents.gemini import (
    API_KEY_ENV,
    DEFAULT_MODEL,
    MAX_PAGE_CHARACTERS,
    MODEL_ENV,
    PROMPT_VERSION,
    GeminiStructure,
)
from sinhala_documents.structure import BlockRole
from sinhala_documents.structuring import StructureUnavailable

PAGE = "1.1 ආරම්භය\nකාර්මික විප්ලවය ඇරඹිණි."


def _reply(items: list[dict]) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(items)}]}}]}


def _adapter(reply, *, recorder: dict | None = None) -> GeminiStructure:
    def post(url, body, *, timeout, api_key):
        if recorder is not None:
            recorder.update(url=url, body=body, timeout=timeout, api_key=api_key)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return GeminiStructure(api_key="test-key", post=post)


def test_a_well_formed_reply_becomes_blocks() -> None:
    adapter = _adapter(
        _reply(
            [
                {"role": "heading", "level": 2, "text": "1.1 ආරම්භය"},
                {"role": "paragraph", "text": "කාර්මික විප්ලවය ඇරඹිණි."},
            ]
        )
    )
    blocks = adapter.blocks_for(PAGE)
    assert [b.role for b in blocks] == [BlockRole.HEADING, BlockRole.PARAGRAPH]
    assert blocks[0].level == 2


def test_the_version_names_the_model_and_the_prompt() -> None:
    """A page structured by a different prompt is a different structuring."""
    adapter = GeminiStructure(api_key="k", model="gemini-x")
    assert adapter.version == f"gemini/gemini-x/prompt-{PROMPT_VERSION}"


def test_the_model_comes_from_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MODEL_ENV, "gemini-from-env")
    assert "gemini-from-env" in GeminiStructure(api_key="k").version
    monkeypatch.delenv(MODEL_ENV)
    assert DEFAULT_MODEL in GeminiStructure(api_key="k").version


def test_the_key_is_sent_as_a_header_not_in_the_url() -> None:
    """A key in a query string is recorded by proxies and repeated in errors."""
    seen: dict = {}
    _adapter(_reply([{"role": "paragraph", "text": PAGE}]), recorder=seen).blocks_for(PAGE)
    assert seen["api_key"] == "test-key"
    assert "test-key" not in seen["url"]


def test_the_page_is_sent_with_a_deterministic_temperature() -> None:
    seen: dict = {}
    _adapter(_reply([{"role": "paragraph", "text": PAGE}]), recorder=seen).blocks_for(PAGE)
    assert seen["body"]["generationConfig"]["temperature"] == 0
    assert PAGE in seen["body"]["contents"][0]["parts"][0]["text"]


def test_no_key_is_unavailable_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(StructureUnavailable, match=API_KEY_ENV):
        GeminiStructure().blocks_for(PAGE)


def test_an_empty_page_is_not_sent_at_all() -> None:
    """No key needed, and no request made, for a page with nothing on it."""
    assert GeminiStructure(api_key="").blocks_for("   \n ") == ()


def test_an_oversized_page_is_not_sent() -> None:
    """A cost limit. A page far larger than a textbook page means extraction broke."""
    with pytest.raises(StructureUnavailable, match="limit"):
        _adapter(_reply([])).blocks_for("අ" * (MAX_PAGE_CHARACTERS + 1))


def test_an_http_error_is_unavailable() -> None:
    error = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
    with pytest.raises(StructureUnavailable, match="429"):
        _adapter(error).blocks_for(PAGE)


def test_a_network_error_is_unavailable() -> None:
    with pytest.raises(StructureUnavailable):
        _adapter(urllib.error.URLError("no route to host")).blocks_for(PAGE)


def test_a_timeout_is_unavailable() -> None:
    with pytest.raises(StructureUnavailable):
        _adapter(TimeoutError("timed out")).blocks_for(PAGE)


def test_a_blocked_response_with_no_content_is_unavailable() -> None:
    """Safety filters return candidates with no parts."""
    with pytest.raises(StructureUnavailable, match="no content"):
        _adapter({"candidates": [{"finishReason": "SAFETY"}]}).blocks_for(PAGE)


def test_a_non_json_reply_is_unavailable() -> None:
    reply = {"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]}
    with pytest.raises(StructureUnavailable, match="not JSON"):
        _adapter(reply).blocks_for(PAGE)


def test_a_reply_that_is_not_a_list_is_unavailable() -> None:
    with pytest.raises(StructureUnavailable, match="list"):
        _adapter(_reply({"role": "paragraph"})).blocks_for(PAGE)  # type: ignore[arg-type]


def test_an_unknown_role_is_unavailable_rather_than_guessed() -> None:
    """Guessing is how a misparse becomes wrong structure that still verifies."""
    with pytest.raises(StructureUnavailable, match="unknown block role"):
        _adapter(_reply([{"role": "sidebar", "text": PAGE}])).blocks_for(PAGE)


def test_a_block_without_text_is_unavailable() -> None:
    with pytest.raises(StructureUnavailable, match="no text"):
        _adapter(_reply([{"role": "paragraph"}])).blocks_for(PAGE)


def test_a_heading_without_a_level_gets_the_deepest_one() -> None:
    """It nests under what came before instead of restructuring the document."""
    blocks = _adapter(_reply([{"role": "heading", "text": "ආරම්භය"}])).blocks_for(PAGE)
    assert blocks[0].level == 3


def test_an_out_of_range_level_is_not_believed() -> None:
    blocks = _adapter(_reply([{"role": "heading", "level": 99, "text": "ආරම්භය"}])).blocks_for(PAGE)
    assert blocks[0].level == 3


def test_a_level_on_something_that_is_not_a_heading_is_dropped() -> None:
    """Block would reject it, and the model offering one is not worth failing over."""
    blocks = _adapter(_reply([{"role": "paragraph", "level": 2, "text": PAGE}])).blocks_for(PAGE)
    assert blocks[0].level is None


def test_running_heads_and_page_numbers_are_not_offered_to_the_model() -> None:
    """They decide what is *not* narrated, so over-applying them removes text.

    A model that labels a sentence as a running header makes it silently
    disappear from the audio. Those two stay deterministic.
    """
    seen: dict = {}
    _adapter(_reply([{"role": "paragraph", "text": PAGE}]), recorder=seen).blocks_for(PAGE)
    offered = seen["body"]["generationConfig"]["responseSchema"]["items"]["properties"]["role"]
    assert BlockRole.RUNNING_HEAD.value not in offered["enum"]
    assert BlockRole.PAGE_NUMBER.value not in offered["enum"]
    assert BlockRole.CAPTION.value in offered["enum"]


def test_a_wrong_answer_is_returned_rather_than_raised() -> None:
    """The distinction the whole design rests on.

    Unavailable means use the deterministic structure and carry on. Wrong means
    verification rejects it and somebody is told. Raising here would turn the
    second into the first and lose the only signal a model is misbehaving.
    """
    blocks = _adapter(_reply([{"role": "paragraph", "text": "නොතිබූ වාක්‍යයක්"}])).blocks_for(PAGE)
    assert blocks  # returned, not raised
