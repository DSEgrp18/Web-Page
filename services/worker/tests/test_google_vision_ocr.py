"""Cloud Vision parsing, batching, and bounded per-page fallback."""

from __future__ import annotations

from types import SimpleNamespace as NS

from sinhala_documents.google_vision_ocr import (
    MAX_ENCODED_BYTES,
    MAX_IMAGES_PER_REQUEST,
    GoogleVisionOcr,
    clean_words,
    words_from_annotation,
)
from sinhala_documents.model import PageExtraction, PageKind
from sinhala_documents.ocr import OcrAdapter, OcrPageResult, OcrWord


def _symbol(text: str, break_type: int | None = None) -> NS:
    detected_break = NS(type_=break_type) if break_type is not None else None
    return NS(text=text, property=NS(detected_break=detected_break))


def _vision_word(text: str, *, left: int, top: int, confidence: float = 0.9) -> NS:
    vertices = [NS(x=left, y=top), NS(x=left + 50, y=top + 20)]
    symbols = [_symbol(character) for character in text]
    symbols[-1] = _symbol(symbols[-1].text, 5)
    return NS(symbols=symbols, bounding_box=NS(vertices=vertices), confidence=confidence)


def _annotation(*words: NS, width: int = 1000, height: int = 1400) -> NS:
    paragraph = NS(words=list(words))
    return NS(pages=[NS(width=width, height=height, blocks=[NS(paragraphs=[paragraph])])])


def _word(text: str, *, top: int = 100, confidence: float = 90, line: int = 1) -> OcrWord:
    return OcrWord(text, 20, top, 50, 20, 1, 1, line, confidence)


def _page(index: int) -> PageExtraction:
    return PageExtraction(
        page_index=index,
        page_label=str(index + 1),
        width=595,
        height=842,
        kind=PageKind.IMAGE,
        lines=(),
        image_count=1,
        notes=(),
    )


def test_parser_preserves_mixed_sinhala_english_numbers_codes_and_labels() -> None:
    annotation = _annotation(
        _vision_word("විභාගය", left=20, top=100),
        _vision_word("English", left=100, top=100),
        _vision_word("2026", left=200, top=100),
        _vision_word("AL/2026/71/S-I", left=300, top=100),
        _vision_word("(iv)", left=500, top=100),
    )

    words, width, height = words_from_annotation(annotation)

    assert [word.text for word in words] == [
        "විභාගය",
        "English",
        "2026",
        "AL/2026/71/S-I",
        "(iv)",
    ]
    assert (width, height) == (1000, 1400)
    assert all(word.confidence == 90 for word in words)


def test_cleanup_drops_edge_noise_but_keeps_uncertain_body_text() -> None:
    words = (
        _word("|", top=1, confidence=1),
        _word("7", top=1, confidence=1),
        _word("අ", top=500, confidence=1, line=2),
        _word("•", top=500, confidence=99, line=2),
    )

    cleaned = clean_words(words, page_width=1000, page_height=1400)

    assert [word.text for word in cleaned] == ["අ"]


def test_batches_obey_request_count_and_encoded_size_limits() -> None:
    images = [(index, b"x" * 700_000) for index in range(20)]

    batches = list(GoogleVisionOcr._batches(images))

    assert [len(batch) for batch in batches] == [8, 8, 4]
    assert all(len(batch) <= MAX_IMAGES_PER_REQUEST for batch in batches)
    assert all(
        sum(4 * ((len(data) + 2) // 3) for _, data in batch) <= MAX_ENCODED_BYTES
        for batch in batches
    )


class _Fallback(OcrAdapter):
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    @property
    def version(self) -> str:
        return "fallback/1"

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        self.calls.append(image_png)
        return (_word("fallback"),)


class _PartialVision(GoogleVisionOcr):
    def _recognise_pdf(self, source, pages):
        return {pages[0].page_index: OcrPageResult((_word("cloud"),), 72)}


def test_only_failed_pages_use_local_fallback_and_order_is_stable() -> None:
    fallback = _Fallback()
    adapter = _PartialVision(fallback=fallback)
    rendered: list[int] = []

    def render(_source, page_index, *, dpi):
        rendered.append(page_index)
        return f"page-{page_index}".encode()

    results = adapter.recognise_document(
        b"%PDF tiny", [_page(0), _page(1), _page(2)], dpi=300, render=render
    )

    assert list(results) == [0, 1, 2]
    assert results[0].words[0].text == "cloud"
    assert [results[index].words[0].text for index in (1, 2)] == ["fallback", "fallback"]
    assert rendered == [1, 2]
    assert fallback.calls == [b"page-1", b"page-2"]


def test_the_local_fallback_reads_sinhala_alone() -> None:
    """sin+eng measured worse and slower: English words invented from Sinhala."""
    assert "/sin/" in GoogleVisionOcr().version.split("fallback-", 1)[1]
