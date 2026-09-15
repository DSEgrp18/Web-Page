"""Recognised text: what it may be, and what it is always marked as.

Most of these need no Tesseract: they feed the adapter's output format in
directly, because the rules about what recognised text becomes are ours and
must hold whatever engine produced it. The last test runs the real engine and
is skipped where it is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace

import pytest
from pdf_fixtures import build_pdf, legacy_page, sinhala_page

from sinhala_documents import prepare_document
from sinhala_documents.model import (
    BoundingBox,
    ExtractionMethod,
    PageExtraction,
    PageKind,
    QualityState,
    TextLine,
    TextSpan,
)
from sinhala_documents.ocr import (
    NOTE,
    OcrAdapter,
    OcrMode,
    OcrUnavailable,
    OcrWord,
    TesseractOcr,
    lines_from_words,
    normalise,
    parse_tsv,
    recognise_page,
    text_layer_failed,
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


# --------------------------------------------------------------------------
# Which pages are read from their image
# --------------------------------------------------------------------------


def line_of(text: str) -> TextLine:
    box = BoundingBox(0, 0, 10, 10)
    return TextLine(spans=(TextSpan(text=text, font="", raw_font="", size=12, box=box),), box=box)


def page_with(*texts: str, kind: PageKind = PageKind.TEXT, undecodable: bool = False):
    lines = tuple(line_of(text) for text in texts)
    if undecodable:
        bad = replace(lines[0].spans[0], quality=QualityState.UNDECODABLE)
        lines = (TextLine(spans=(bad,), box=lines[0].box), *lines[1:])
    return broken_page(kind=kind, lines=lines, notes=())


SENTENCE = "කීර්තිය හා ධනය වර්ධනය කර ගැනීමේ අරමුණෙන්"
OTHER = "නව ප්‍රදේශ සොයා ජනාවාස පිහිටුවා ගැනීමට"


def test_a_page_holding_a_hidden_copy_of_itself_has_a_failed_text_layer() -> None:
    """Page 121: every line twice."""
    assert text_layer_failed(page_with(SENTENCE, SENTENCE, OTHER, OTHER))


def test_one_repeated_line_is_not_enough() -> None:
    """A refrain or a repeated heading is ordinary."""
    assert not text_layer_failed(page_with(SENTENCE, OTHER, SENTENCE))


def test_short_repeats_do_not_count() -> None:
    assert not text_layer_failed(page_with("1.", "1.", "2.", "2.", "3.", "3."))


def test_a_withheld_line_means_the_text_layer_failed() -> None:
    assert text_layer_failed(page_with(SENTENCE, undecodable=True))


def test_a_withheld_stray_symbol_is_not_worth_recognising_the_page_for() -> None:
    """Pages 53, 129, 155 and 168 withheld only "=", "a", "S" and "•"."""
    assert not text_layer_failed(page_with("•  ", SENTENCE, OTHER, undecodable=True))


def test_a_stray_symbol_inside_a_readable_line_does_not_count_the_line() -> None:
    """How it really looked: "=" withheld in the middle of a line of good Sinhala."""
    box = BoundingBox(0, 0, 10, 10)
    good = TextSpan(text=SENTENCE, font="", raw_font="", size=12, box=box)
    stray = replace(good, text="=", quality=QualityState.UNDECODABLE)
    mixed = TextLine(spans=(good, stray, good), box=box)

    assert not text_layer_failed(broken_page(lines=(mixed,), notes=(), kind=PageKind.TEXT))
    # And a real withheld sentence in the same position still does.
    sentence = replace(stray, text="m<d; a no Pkoa rdcH ks,Odßka")
    real = TextLine(spans=(good, sentence), box=box)
    assert text_layer_failed(broken_page(lines=(real,), notes=(), kind=PageKind.TEXT))


def test_a_scan_has_a_failed_text_layer() -> None:
    assert text_layer_failed(page_with(kind=PageKind.IMAGE))


def test_a_clean_page_does_not() -> None:
    assert not text_layer_failed(page_with(SENTENCE, OTHER))


class CountingOcr(FakeOcr):
    def __init__(self, words=None, error=None, version="fake/1"):
        super().__init__(words if words is not None else (word("පිළිගත් පාඨය"),), error)
        self.calls = 0
        self._version = version

    @property
    def version(self) -> str:
        return self._version

    def recognise(self, image_png: bytes):
        self.calls += 1
        # A real render of the fixture page, not a placeholder.
        assert image_png.startswith(b"\x89PNG")
        return super().recognise(image_png)


def test_broken_mode_reads_only_the_broken_page_from_its_image() -> None:
    pdf = build_pdf([sinhala_page(), legacy_page("DL-Manel")])
    ocr = CountingOcr()

    document = prepare_document(pdf, ocr=ocr, ocr_mode=OcrMode.BROKEN)

    assert ocr.calls == 1
    good, broken = document.pages
    # The clean page keeps its exact embedded text.
    assert all("පිළිගත් පාඨය" not in s.display_text for s in good.segments)
    # The page that had nothing to read now does.
    assert [s.display_text for s in broken.segments] == ["පිළිගත් පාඨය"]
    assert broken.quality is QualityState.NEEDS_REVIEW
    assert NOTE in broken.notes


def test_all_mode_reads_every_page_from_its_image() -> None:
    pdf = build_pdf([sinhala_page(), legacy_page("DL-Manel")])
    ocr = CountingOcr()

    document = prepare_document(pdf, ocr=ocr, ocr_mode=OcrMode.ALL)

    assert ocr.calls == 2
    assert all(page.quality is QualityState.NEEDS_REVIEW for page in document.pages)


def test_off_is_exactly_the_document_without_ocr() -> None:
    """Including its version, so books prepared before OCR keep their audio."""
    pdf = build_pdf([sinhala_page(), legacy_page("DL-Manel")])
    ocr = CountingOcr()

    with_off = prepare_document(pdf, ocr=ocr, ocr_mode=OcrMode.OFF)
    without = prepare_document(pdf)

    assert ocr.calls == 0
    assert with_off.version == without.version
    assert with_off.segments == without.segments


def test_recognition_changes_the_version_and_so_the_audio_cache() -> None:
    pdf = build_pdf([legacy_page("DL-Manel")])

    plain = prepare_document(pdf).version
    broken = prepare_document(pdf, ocr=CountingOcr(), ocr_mode=OcrMode.BROKEN).version
    everything = prepare_document(pdf, ocr=CountingOcr(), ocr_mode=OcrMode.ALL).version
    newer_engine = prepare_document(
        pdf, ocr=CountingOcr(version="fake/2"), ocr_mode=OcrMode.BROKEN
    ).version

    assert len({plain, broken, everything, newer_engine}) == 4


def test_without_an_engine_the_book_is_still_prepared_and_says_what_is_unread() -> None:
    """Missing Tesseract must not take away the pages that read perfectly well."""
    pdf = build_pdf([sinhala_page(), legacy_page("DL-Manel")])
    ocr = CountingOcr(error=OcrUnavailable("Tesseract is not installed."))

    document = prepare_document(pdf, ocr=ocr, ocr_mode=OcrMode.BROKEN)

    assert [page.has_audio for page in document.pages] == [True, False]
    assert any("could not be read by optical character recognition" in n for n in document.notes)
    assert any("not installed" in n for n in document.notes)
