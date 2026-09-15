"""Which pages a deployment reads from their image, and what it is told about it."""

from __future__ import annotations

import pytest
from sinhala_documents.ocr import OcrMode, TesseractOcr

from sinhala_reader.recognition import OCR_ENV, build_ocr, ocr_limitations, ocr_mode


def test_the_default_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off unless chosen: recognition needs an engine a test machine may not have."""
    monkeypatch.delenv(OCR_ENV, raising=False)
    assert ocr_mode() is OcrMode.OFF
    assert build_ocr() is None


@pytest.mark.parametrize("value", ["broken", "all", " Broken "])
def test_a_mode_is_selected_by_configuration(monkeypatch: pytest.MonkeyPatch, value) -> None:
    monkeypatch.setenv(OCR_ENV, value)
    assert ocr_mode().value == value.strip().lower()
    assert isinstance(build_ocr(), TesseractOcr)


def test_an_unrecognised_value_stops_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not quietly leave a book's broken pages unread."""
    monkeypatch.setenv(OCR_ENV, "brokn")
    with pytest.raises(ValueError, match="brokn"):
        ocr_mode()


def test_off_names_what_a_reader_loses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OCR_ENV, raising=False)
    [note] = ocr_limitations()
    assert "stays unread" in note
    assert OCR_ENV in note


def test_on_says_text_may_be_misread_and_stays_on_the_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    notes = " ".join(ocr_limitations())
    assert "misread" in notes
    assert "nothing is sent elsewhere" in notes


def test_a_missing_engine_is_reported_rather_than_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OCR_ENV, "all")
    monkeypatch.setenv("SINHALA_READER_TESSERACT", "no-such-tesseract-binary")
    assert any("not installed" in note for note in ocr_limitations())


def test_readiness_reports_the_recognition_mode(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OCR_ENV, raising=False)
    body = client.get("/readiness").json()
    assert body["ocr"] == "off"
    assert any("stays unread" in note for note in body["limitations"])
