"""Which structure source a deployment gets, and what it is told about it."""

from __future__ import annotations

import pytest
from sinhala_documents.gemini import GeminiStructure
from sinhala_documents.structuring import DeterministicStructure

from sinhala_reader.structure import (
    STRUCTURE_ENV,
    build_structure,
    structure_limitations,
    structure_mode,
)


def test_the_default_is_no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structure sends a reader's page to an external service. Opt in, never out."""
    monkeypatch.delenv(STRUCTURE_ENV, raising=False)
    assert structure_mode() == "deterministic"
    assert isinstance(build_structure(), DeterministicStructure)


def test_gemini_is_selected_by_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STRUCTURE_ENV, "gemini")
    assert isinstance(build_structure(), GeminiStructure)


def test_an_unrecognised_value_stops_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not quietly change what readers get."""
    monkeypatch.setenv(STRUCTURE_ENV, "gemeni")
    with pytest.raises(ValueError, match="gemeni"):
        build_structure()


def test_the_deterministic_limitation_names_the_effect_on_a_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not "structure is off" but what that does to somebody listening."""
    monkeypatch.delenv(STRUCTURE_ENV, raising=False)
    (note,) = structure_limitations()
    assert "caption" in note
    assert STRUCTURE_ENV in note


def test_the_gemini_limitation_discloses_that_pages_leave_the_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External processing of a private document has to be disclosed."""
    monkeypatch.setenv(STRUCTURE_ENV, "gemini")
    (note,) = structure_limitations()
    assert "sent to Google" in note
    assert "character for character" in note


def test_readiness_reports_the_structure_source(client) -> None:
    body = client.get("/readiness").json()
    assert body["structure"] == "deterministic"
    assert any("caption" in note for note in body["limitations"])
