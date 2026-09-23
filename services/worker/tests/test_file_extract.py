"""The non-PDF document paths preserve readable Sinhala and honest provenance."""

from io import BytesIO
from zipfile import ZipFile

import pytest

from sinhala_documents import DocumentRejected, check_document_bytes, prepare_document, validation
from sinhala_documents.file_extract import extract_docx
from sinhala_documents.ocr import OcrAdapter, OcrMode, OcrWord


def docx_xml(body: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>",
        )
    return buffer.getvalue()


def docx_bytes(text: str) -> bytes:
    return docx_xml(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>")


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


def test_docx_tabs_keep_words_and_page_numbers_separate() -> None:
    source = docx_xml("<w:p><w:r><w:t>Chapter One</w:t><w:tab/><w:t>5</w:t></w:r></w:p>")

    assert extract_docx(source).pages[0].readable_text == "Chapter One\t5"


def test_docx_line_breaks_do_not_fuse_words() -> None:
    source = docx_xml("<w:p><w:r><w:t>line one</w:t><w:br/><w:t>line two</w:t></w:r></w:p>")

    assert extract_docx(source).pages[0].readable_text == "line one\nline two"


def test_docx_text_box_paragraphs_are_extracted_once() -> None:
    source = docx_xml(
        "<w:p><w:r><w:t>outer</w:t><w:txbxContent>"
        "<w:p><w:r><w:t>boxed</w:t></w:r></w:p>"
        "</w:txbxContent></w:r></w:p>"
    )

    assert extract_docx(source).pages[0].readable_text == "outer\nboxed"


def test_malformed_docx_xml_is_rejected_as_a_document_error() -> None:
    source = docx_xml("<w:p><w:r><w:t>unfinished")

    with pytest.raises(DocumentRejected, match="damaged"):
        check_document_bytes(source, "notes.docx")


def test_docx_xml_is_bounded_before_decompression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "MAX_DOCX_XML_BYTES", 32)

    with pytest.raises(DocumentRejected, match="too large"):
        check_document_bytes(docx_bytes("a" * 40), "notes.docx")


def test_docx_xml_declarations_that_can_expand_entities_are_rejected() -> None:
    source = docx_xml('<!DOCTYPE x [<!ENTITY words "many words">]><w:p/>')

    with pytest.raises(DocumentRejected, match="unsupported XML"):
        check_document_bytes(source, "notes.docx")


def test_standalone_image_text_is_read_by_ocr() -> None:
    source = b"\x89PNG\r\n\x1a\nimage"
    assert check_document_bytes(source, "page.png") == "image/png"

    prepared = prepare_document(
        source, filename="page.png", ocr=SinhalaImageOcr(), ocr_mode=OcrMode.ALL
    )

    assert prepared.segments[0].display_text == "සිංහල"
    assert prepared.pages[0].quality.value == "needs_review"


def test_standalone_image_does_not_run_ocr_when_it_is_off() -> None:
    source = b"\x89PNG\r\n\x1a\nimage"

    prepared = prepare_document(source, filename="page.png", ocr=SinhalaImageOcr())

    assert prepared.segments == ()
    assert "test/sin" not in prepared.version


def test_image_ocr_engine_changes_the_document_version() -> None:
    source = b"\x89PNG\r\n\x1a\nimage"

    first = prepare_document(
        source, filename="page.png", ocr=SinhalaImageOcr(), ocr_mode=OcrMode.ALL
    )

    class NewSinhalaImageOcr(SinhalaImageOcr):
        @property
        def version(self) -> str:
            return "test/sin-2"

    second = prepare_document(
        source, filename="page.png", ocr=NewSinhalaImageOcr(), ocr_mode=OcrMode.ALL
    )
    assert first.version != second.version


def test_extensionless_pdf_is_recognised_from_its_header() -> None:
    assert check_document_bytes(b"%PDF-1.7\n", "scan") == "application/pdf"


def test_extension_and_contents_must_agree() -> None:
    with pytest.raises(DocumentRejected, match="not a PNG"):
        check_document_bytes(b"not an image", "page.png")
