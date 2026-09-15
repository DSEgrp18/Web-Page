"""Recognised text: what it may be, and what it is always marked as.

Most of these need no Tesseract: they feed the adapter's output format in
directly, because the rules about what recognised text becomes are ours and
must hold whatever engine produced it. The last test runs the real engine and
is skipped where it is not installed.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from sinhala_documents.model import ExtractionMethod, PageExtraction, PageKind, QualityState
from sinhala_documents.ocr import (
    NOTE,
    OcrAdapter,
    OcrUnavailable,
    OcrWord,
    TesseractOcr,
    lines_from_words,
    normalise,
    parse_tsv,
    recognise_page,
)

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def row(block, paragraph, line, word, left, top, width, height, text, level=5, conf=90.0):
    return (
        f"{level}\t1\t{block}\t{paragraph}\t{line}\t{word}\t{left}\t{top}\t{width}\t{height}"
        f"\t{conf}\t{text}"
    )


def tsv(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


def word(text, line=1, left=0, top=0, width=30, height=40, block=1, paragraph=1):
    return OcrWord(text, left, top, width, height, block, paragraph, line, 90.0)


# --------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------


def test_the_non_joiner_tesseract_adds_after_al_lakuna_is_removed() -> None:
    """42 of them on page 121. Invisible, and a typed question never contains one."""
    assert normalise("අරමුණෙන්\u200c යුරෝපා") == "අරමුණෙන් යුරෝපා"


def test_the_zero_width_joiner_is_part_of_the_spelling_and_stays() -> None:
    """ප්‍ර and ය need it. CLAUDE.md: preserve joiners."""
    assert normalise("ප්\u200dරදේශ") == "ප්\u200dරදේශ"


def test_a_non_joiner_anywhere_else_is_left_alone() -> None:
    """Only the case measured on a real page is changed."""
    assert normalise("අ\u200cආ") == "අ\u200cආ"


# --------------------------------------------------------------------------
# Reading Tesseract's output
# --------------------------------------------------------------------------


def test_only_word_rows_with_text_become_words() -> None:
    words = parse_tsv(
        tsv(
            row(1, 1, 1, 0, 0, 0, 500, 60, "", level=4),
            row(1, 1, 1, 1, 10, 10, 80, 40, "කීර්තිය"),
            row(1, 1, 1, 2, 100, 10, 30, 40, "   "),
            row(1, 1, 1, 3, 140, 10, 30, 40, "හා"),
        )
    )

    assert [w.text for w in words] == ["කීර්තිය", "හා"]
    assert words[0].left == 10 and words[0].height == 40


def test_a_malformed_row_is_skipped_not_fatal() -> None:
    words = parse_tsv(tsv("5\t1\tnot-a-number", row(1, 1, 1, 1, 0, 0, 10, 10, "හා")))

    assert [w.text for w in words] == ["හා"]


def test_words_become_lines_in_the_order_tesseract_read_them() -> None:
    """Not re-sorted by position: that would undo its column detection."""
    words = (
        word("දකුණ", line=1, left=600, top=100, block=2),
        word("තීරුව", line=1, left=700, top=100, block=2),
        word("වම", line=1, left=10, top=100, block=1),
    )

    lines = lines_from_words(words, dpi=300, version="v")

    # Block 2 was read first, so it comes first, although it is to the right.
    assert [line.text for line in lines] == ["දකුණ තීරුව", "වම"]


def test_boxes_are_converted_from_pixels_to_page_points() -> None:
    lines = lines_from_words(
        (word("හා", left=300, top=600, width=150, height=75),), dpi=300, version="v"
    )

    box = lines[0].box
    # 300 dpi: 300 px is 72 pt.
    assert (box.x0, box.top, box.x1, box.bottom) == (72.0, 144.0, 108.0, 162.0)


def test_a_bullet_read_as_symbols_is_not_read_aloud() -> None:
    """Page 121's ❖ came out as "&*"."""
    lines = lines_from_words(
        (word("&*", left=0), word("කීර්තිය", left=50), word("-", left=90), word("හා", left=120)),
        dpi=300,
        version="v",
    )

    # Leading only. A dash inside a line is text.
    assert lines[0].text == "කීර්තිය - හා"


def test_a_line_of_nothing_but_symbols_is_dropped() -> None:
    assert lines_from_words((word("•"),), dpi=300, version="v") == ()


def test_recognised_text_is_always_marked_for_review() -> None:
    """Narrated, and never presented as checked. OCR confidence is not accuracy."""
    confident = OcrWord("කීර්තිය", 0, 0, 10, 10, 1, 1, 1, confidence=99.9)

    span = lines_from_words((confident,), dpi=300, version="tesseract/5")[0].spans[0]

    assert span.method is ExtractionMethod.OCR
    assert span.quality is QualityState.NEEDS_REVIEW
    assert span.notes == (NOTE,)
    # Provenance: which recogniser read it.
    assert span.raw_font == "tesseract/5"


# --------------------------------------------------------------------------
# Replacing a page
# --------------------------------------------------------------------------


class FakeOcr(OcrAdapter):
    def __init__(self, words=(), error=None):
        self._words = words
        self._error = error

    @property
    def version(self) -> str:
        return "fake/1"

    def recognise(self, image_png: bytes):
        if self._error:
            raise self._error
        return self._words


def broken_page(**overrides) -> PageExtraction:
    fields = dict(
        page_index=120,
        page_label="111",
        width=522.0,
        height=684.0,
        kind=PageKind.MIXED,
        lines=(),
        image_count=2,
        notes=("5 of 44 lines on this page use a legacy Sinhala font and cannot be read yet.",),
    )
    fields.update(overrides)
    return PageExtraction(**fields)


def test_a_recognised_page_keeps_its_identity_and_replaces_its_lines() -> None:
    page = recognise_page(broken_page(), b"png", FakeOcr((word("කීර්තිය"), word("හා", left=40))))

    assert page.page_index == 120
    assert page.page_label == "111"
    assert (page.width, page.height, page.image_count) == (522.0, 684.0, 2)
    assert page.readable_text == "කීර්තිය හා"
    assert page.methods == frozenset({ExtractionMethod.OCR})


def test_the_page_says_it_was_recognised_and_still_mentions_its_images() -> None:
    page = recognise_page(broken_page(), b"png", FakeOcr((word("කීර්තිය"),)))

    assert page.notes[0] == NOTE
    assert any("image" in note for note in page.notes)
    # The old complaint is about text that is no longer what is read.
    assert not any("legacy" in note for note in page.notes)


def test_a_page_recognition_found_nothing_on_is_not_called_text() -> None:
    page = recognise_page(broken_page(image_count=0), b"png", FakeOcr(()))

    assert page.kind is PageKind.EMPTY


def test_a_failure_is_raised_so_the_caller_keeps_the_page_it_had() -> None:
    with pytest.raises(OcrUnavailable):
        recognise_page(broken_page(), b"png", FakeOcr(error=OcrUnavailable("no engine")))


# --------------------------------------------------------------------------
# The Tesseract adapter
# --------------------------------------------------------------------------


def completed(stdout: bytes = b"", returncode: int = 0, stderr: bytes = b""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_it_runs_sinhala_recognition_through_pipes_never_files() -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "--version" in command:
            return completed(b"tesseract 5.3.0\n leptonica-1.82.0\n")
        return completed(tsv(row(1, 1, 1, 1, 0, 0, 10, 10, "හා")).encode())

    ocr = TesseractOcr(executable="tesseract", run=run)
    words = ocr.recognise(b"PNG BYTES")

    command, kwargs = calls[0]
    assert command[:3] == ["tesseract", "stdin", "stdout"]
    assert command[command.index("-l") + 1] == "sin"
    assert kwargs["input"] == b"PNG BYTES"
    assert [w.text for w in words] == ["හා"]
    assert ocr.version == "tesseract/5.3.0/sin/psm3/ocr-1"


def test_no_engine_installed_is_unavailable_not_a_crash() -> None:
    def run(command, **kwargs):
        raise FileNotFoundError(command[0])

    with pytest.raises(OcrUnavailable, match="not installed"):
        TesseractOcr(run=run).recognise(b"png")


def test_a_missing_sinhala_model_is_unavailable() -> None:
    def run(command, **kwargs):
        return completed(returncode=1, stderr=b"Failed loading language 'sin'\n")

    with pytest.raises(OcrUnavailable, match="sin"):
        TesseractOcr(run=run).recognise(b"png")


def test_a_page_that_takes_too_long_is_unavailable() -> None:
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(OcrUnavailable, match="longer"):
        TesseractOcr(run=run, timeout=5).recognise(b"png")


def _has_sinhala_tesseract() -> bool:
    if shutil.which("tesseract") is None:
        return False
    listed = subprocess.run(["tesseract", "--list-langs"], capture_output=True, check=False)
    return b"sin" in listed.stdout.split()


@pytest.mark.skipif(not _has_sinhala_tesseract(), reason="Tesseract with Sinhala is not installed")
def test_the_real_engine_reports_its_version() -> None:
    """The contract against the real engine, where it exists.

    Recognition quality is not asserted: there is no Sinhala page fixture here
    whose ground truth is established, and a test that passed on whatever came
    out would prove nothing.
    """
    assert TesseractOcr().version.startswith("tesseract/")
    assert "unavailable" not in TesseractOcr().version
