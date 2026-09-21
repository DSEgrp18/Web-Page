"""The non-PDF document paths preserve readable Sinhala and honest provenance."""

from io import BytesIO
from zipfile import ZipFile

import pytest

from sinhala_documents import DocumentRejected, check_document_bytes, prepare_document
from sinhala_documents.ocr import OcrAdapter, OcrWord


def docx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buffer.getvalue()


class SinhalaImageOcr(OcrAdapter):
    @property
    def version(self) -> str:
        return "test/sin"

    def recognise(self, image_png: bytes) -> tuple[OcrWord, ...]:
        assert image_png.startswith(b"\x89PNG")
        return (OcrWord("සිංහල", 10, 10, 80, 20, 1, 1, 1, 95.0),)


def test_docx_paragraphs_become_readable_segments() -> None:
    source = docx_bytes("සිංහල ලේඛනයකි.")
    assert check_document_bytes(source, "notes.docx").endswith("wordprocessingml.document")

    prepared = prepare_document(source, filename="notes.docx")

    assert prepared.segments[0].display_text == "සිංහල ලේඛනයකි."
    assert prepared.pages[0].page_index == 0


def test_standalone_image_text_is_read_by_ocr() -> None:
    source = b"\x89PNG\r\n\x1a\nimage"
    assert check_document_bytes(source, "page.png") == "image/png"

    prepared = prepare_document(source, filename="page.png", ocr=SinhalaImageOcr())

    assert prepared.segments[0].display_text == "සිංහල"
    assert prepared.pages[0].quality.value == "needs_review"


def test_extension_and_contents_must_agree() -> None:
    with pytest.raises(DocumentRejected, match="not a PNG"):
        check_document_bytes(b"not an image", "page.png")
