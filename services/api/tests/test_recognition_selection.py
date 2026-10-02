"""Which recognition engine a deployment uses, and what readiness says about it."""

from __future__ import annotations

import pytest
from sinhala_documents.ocr import OcrMode, TesseractOcr
from sinhala_documents.trocr_ocr import TrocrSinhalaOcr

from sinhala_reader.recognition import (
    CHECKPOINT_ENV,
    ENGINE_ENV,
    OCR_ENV,
    build_ocr,
    ocr_engine,
    ocr_limitations,
    ocr_mode,
)


def test_the_default_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off unless chosen: recognition needs an engine a test machine may not have."""
    monkeypatch.delenv(OCR_ENV, raising=False)
    monkeypatch.delenv(ENGINE_ENV, raising=False)
    assert ocr_mode() is OcrMode.OFF
    assert build_ocr() is None


@pytest.mark.parametrize("value", ["broken", "all", " Broken "])
def test_a_mode_is_selected_by_configuration(monkeypatch: pytest.MonkeyPatch, value) -> None:
    monkeypatch.setenv(OCR_ENV, value)
    monkeypatch.delenv(ENGINE_ENV, raising=False)
    assert ocr_mode().value == value.strip().lower()
    assert isinstance(build_ocr(), TesseractOcr)
    assert ocr_engine() == "tesseract"


def test_trocr_is_selected_by_engine_and_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    monkeypatch.setenv(ENGINE_ENV, "trocr")
    monkeypatch.setenv(CHECKPOINT_ENV, "ransaka")
    adapter = build_ocr()
    assert isinstance(adapter, TrocrSinhalaOcr)
    assert adapter.checkpoint.alias == "ransaka"
    assert "trocr/ransaka@" in adapter.version


def test_eshangj_is_the_trocr_default_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "all")
    monkeypatch.setenv(ENGINE_ENV, "trocr")
    monkeypatch.delenv(CHECKPOINT_ENV, raising=False)
    adapter = build_ocr()
    assert isinstance(adapter, TrocrSinhalaOcr)
    assert adapter.checkpoint.alias == "eshangj"


def test_an_unrecognised_mode_stops_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not quietly leave a book's broken pages unread."""
    monkeypatch.setenv(OCR_ENV, "brokn")
    with pytest.raises(ValueError, match="brokn"):
        ocr_mode()


def test_an_unrecognised_engine_stops_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    monkeypatch.setenv(ENGINE_ENV, "easyocr")
    with pytest.raises(ValueError, match="easyocr"):
        ocr_engine()


def test_an_unrecognised_checkpoint_stops_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    monkeypatch.setenv(ENGINE_ENV, "trocr")
    monkeypatch.setenv(CHECKPOINT_ENV, "surya")
    with pytest.raises(ValueError, match="surya"):
        build_ocr()


def test_off_names_what_a_reader_loses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OCR_ENV, raising=False)
    [note] = ocr_limitations()
    assert "stays unread" in note
    assert OCR_ENV in note


def test_tesseract_says_text_may_be_misread_and_stays_on_the_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    monkeypatch.delenv(ENGINE_ENV, raising=False)
    notes = " ".join(ocr_limitations())
    assert "misread" in notes
    assert "nothing is sent elsewhere" in notes
    assert "Tesseract" in notes


def test_trocr_limitations_name_the_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "all")
    monkeypatch.setenv(ENGINE_ENV, "trocr")
    monkeypatch.setenv(CHECKPOINT_ENV, "eshangj")
    notes = " ".join(ocr_limitations())
    assert "TrOCR" in notes
    assert "eshangj" in notes
    assert "nothing is sent elsewhere" in notes


def test_a_missing_tesseract_is_reported_rather_than_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OCR_ENV, "all")
    monkeypatch.delenv(ENGINE_ENV, raising=False)
    monkeypatch.setenv("SINHALA_READER_TESSERACT", "no-such-tesseract-binary")
    assert any("not installed" in note for note in ocr_limitations())


def test_readiness_reports_the_recognition_mode(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OCR_ENV, raising=False)
    monkeypatch.delenv(ENGINE_ENV, raising=False)
    body = client.get("/readiness").json()
    assert body["ocr"] == "off"
    assert body["ocr_engine"] == "off"
    assert body["ocr_trocr_checkpoint"] is None
    assert any("stays unread" in note for note in body["limitations"])


def test_readiness_reports_trocr_checkpoint(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OCR_ENV, "broken")
    monkeypatch.setenv(ENGINE_ENV, "trocr")
    monkeypatch.setenv(CHECKPOINT_ENV, "ransaka")
    body = client.get("/readiness").json()
    assert body["ocr"] == "broken"
    assert body["ocr_engine"] == "trocr"
    assert body["ocr_trocr_checkpoint"] == "ransaka"
