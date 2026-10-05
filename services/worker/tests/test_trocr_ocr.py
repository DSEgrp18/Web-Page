"""TrOCR Sinhala adapter: layout from Tesseract-shaped words, text from a line model.

These tests never download a Hub checkpoint and never require Pillow or torch.
A fake line recogniser, fake layout adapter, and fake page image exercise the
crop-and-replace path that production uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sinhala_documents.ocr import OcrAdapter, OcrUnavailable, OcrWord
from sinhala_documents.trocr_ocr import (
    CHECKPOINTS,
    TrocrSinhalaOcr,
    resolve_checkpoint,
)


class FixedLayout(OcrAdapter):
    def __init__(self, words: tuple[OcrWord, ...]) -> None:
        self._words = words

    @property
    def version(self) -> str:
        return "fake-layout/1"

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        return self._words


class FakeCrop:
    def __init__(self, box: tuple[int, int, int, int]) -> None:
        self.box = box


class FakePage:
    def __init__(self, width: int = 200, height: int = 120) -> None:
        self.size = (width, height)
        self.crops: list[tuple[int, int, int, int]] = []

    def crop(self, box: tuple[int, int, int, int]) -> FakeCrop:
        self.crops.append(box)
        return FakeCrop(box)


def test_resolve_checkpoint_defaults_to_eshangj(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SINHALA_READER_TROCR_CHECKPOINT", raising=False)
    assert resolve_checkpoint().alias == "eshangj"
    assert resolve_checkpoint("ransaka").hub_id == CHECKPOINTS["ransaka"].hub_id


def test_version_names_the_checkpoint_and_layout() -> None:
    adapter = TrocrSinhalaOcr(
        checkpoint="eshangj",
        layout=FixedLayout(()),
        recognise_line=lambda _crop: "ක",
        open_image=lambda _png: FakePage(),
    )
    assert adapter.version.startswith("trocr/eshangj@0c1687c/detect-fake-layout/1/")
    assert "ransaka" not in adapter.version


def test_line_crops_keep_geometry_and_use_trocr_text() -> None:
    layout = FixedLayout(
        (
            OcrWord("wrong", 10, 10, 80, 30, 1, 1, 1, 90.0),
            OcrWord("also", 100, 10, 70, 30, 1, 1, 1, 90.0),
            OcrWord("ignored", 10, 60, 160, 30, 1, 1, 2, 90.0),
        )
    )
    texts = iter(["පළමු පේළිය", "දෙවන පේළිය"])
    page = FakePage()

    adapter = TrocrSinhalaOcr(
        checkpoint="ransaka",
        layout=layout,
        recognise_line=lambda _crop: next(texts),
        open_image=lambda _png: page,
    )
    words = adapter.recognise(b"not-a-real-png")

    assert [word.text for word in words] == ["පළමු පේළිය", "දෙවන පේළිය"]
    assert words[0].left == 10 and words[0].top == 10
    assert words[0].width == 160  # union of the two layout words on line 1
    assert words[0].block == 1 and words[0].line == 1
    assert words[1].top == 60 and words[1].line == 2
    assert "trocr/ransaka@" in adapter.version
    assert len(page.crops) == 2


def test_empty_layout_yields_no_words() -> None:
    adapter = TrocrSinhalaOcr(
        layout=FixedLayout(()),
        recognise_line=lambda _crop: "should-not-run",
        open_image=lambda _png: FakePage(),
    )
    assert adapter.recognise(b"png") == ()


def test_blank_trocr_lines_fall_back_to_layout_text() -> None:
    layout = FixedLayout((OcrWord("x", 10, 10, 50, 20, 1, 1, 1, 50.0),))
    adapter = TrocrSinhalaOcr(
        layout=layout,
        recognise_line=lambda _crop: "   ",
        open_image=lambda _png: FakePage(),
    )
    words = adapter.recognise(b"png")
    assert [word.text for word in words] == ["x"]


def test_blank_trocr_fallback_preserves_a_whole_tesseract_line() -> None:
    layout = FixedLayout(
        (
            OcrWord("2026", 10, 10, 40, 20, 1, 1, 1, 90.0),
            OcrWord("PDF", 60, 10, 40, 20, 1, 1, 1, 90.0),
        )
    )
    adapter = TrocrSinhalaOcr(
        layout=layout,
        recognise_line=lambda _crop: "",
        open_image=lambda _png: FakePage(),
    )

    [word] = adapter.recognise(b"png")

    assert word.text == "2026 PDF"
    assert (word.left, word.top, word.width, word.height) == (10, 10, 90, 20)


def test_missing_torch_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment that selected Trocr without installing it must fail loudly."""

    class ExplodingLayout(OcrAdapter):
        @property
        def version(self) -> str:
            return "unused"

        def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
            return (OcrWord("x", 10, 10, 20, 20, 1, 1, 1, 1.0),)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"torch", "transformers"} or name.startswith("transformers."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    adapter = TrocrSinhalaOcr(
        layout=ExplodingLayout(),
        open_image=lambda _png: FakePage(),
    )
    with pytest.raises(OcrUnavailable, match="torch and transformers"):
        adapter.recognise(b"png")


def _local_checkpoint_dir() -> Path | None:
    for candidate in (
        Path("models/trocr_sinhala_eshangj"),
        Path("models/trocr_sinhala_ransaka"),
        Path("/models/trocr_sinhala"),
    ):
        if (candidate / "config.json").is_file():
            return candidate
    return None


@pytest.mark.skipif(
    _local_checkpoint_dir() is None,
    reason="No local TrOCR checkpoint under models/; see docs/trocr-sinhala-ocr.md",
)
def test_real_checkpoint_reads_a_line_crop() -> None:
    """Smoke only: proves the Hub weights load and emit text from a crop."""
    pytest.importorskip("PIL")
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from PIL import Image, ImageDraw

    model_dir = _local_checkpoint_dir()
    assert model_dir is not None
    alias = "ransaka" if "ransaka" in model_dir.name else "eshangj"
    image = Image.new("RGB", (320, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.text((8, 16), "test", fill="black")
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    layout = FixedLayout((OcrWord("x", 0, 0, 320, 64, 1, 1, 1, 1.0),))
    adapter = TrocrSinhalaOcr(
        checkpoint=alias,
        model_dir=str(model_dir),
        device="cpu",
        layout=layout,
    )
    words = adapter.recognise(png)
    assert words
    assert words[0].text.strip()
