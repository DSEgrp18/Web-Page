"""Chapters, from the book's own typography.

The fixtures mirror the Grade 11 history textbook the thresholds were measured
on: 12 pt body, chapter numbers at 27 pt, titles at 20 pt either side of the
number, a contents page at 18-20 pt. The test that matters most is the one that
finds nothing, because the failure CLAUDE.md warns about is not a missing
chapter list but a confident, wrong one.
"""

from __future__ import annotations

from pdf_fixtures import Page, Text, build_pdf, sinhala_page

from sinhala_documents import extract_document, prepare_document
from sinhala_documents.chapters import Chapter, find_chapters

BODY = tuple(Text("කාර්මික විප්ලවය ආරම්භ විය", y=600 - index * 16) for index in range(20))


def opener(*title: Text) -> Page:
    return Page(blocks=(*title, *BODY))


def chapters_of(*pages: Page) -> tuple[Chapter, ...]:
    return find_chapters(extract_document(build_pdf(list(pages))))


def test_a_number_and_title_on_one_line_are_separated() -> None:
    found = chapters_of(
        opener(Text("01 කාර්මික විප්ලවය", size=27, y=740)),
        sinhala_page(),
        opener(Text("02 ජාතික පුනරුදය", size=27, y=740)),
    )

    assert found == (
        Chapter(title="කාර්මික විප්ලවය", page_index=0, number="01"),
        Chapter(title="ජාතික පුනරුදය", page_index=2, number="02"),
    )


def test_a_number_between_title_lines_does_not_split_the_title() -> None:
    """Page 28 of the textbook: a title line, the number beside it, the rest."""
    found = chapters_of(
        opener(
            Text("ශ්‍රී ලංකාවේ", size=23, y=740),
            Text("02", size=27, x=400, y=730),
            Text("බ්‍රිතාන්‍ය බලය පිහිටුවීම", size=23, y=715),
        ),
        opener(Text("03 ජාතික පුනරුදය", size=27, y=740)),
    )

    assert found[0] == Chapter(title="ශ්‍රී ලංකාවේ බ්‍රිතාන්‍ය බලය පිහිටුවීම", page_index=0, number="02")


def test_a_contents_page_is_not_a_chapter() -> None:
    """Its heading is large, but not chapter-opener large."""
    contents = Page(
        blocks=(
            Text("පටුන", size=20, y=740),
            Text("1. කාර්මික විප්ලවය", size=18, y=715),
            Text("2. ජාතික පුනරුදය", size=18, y=690),
            *BODY,
        )
    )
    found = chapters_of(
        contents,
        opener(Text("01 කාර්මික විප්ලවය", size=27, y=740)),
        opener(Text("02 ජාතික පුනරුදය", size=27, y=740)),
    )

    assert [chapter.page_index for chapter in found] == [1, 2]


def test_large_text_low_on_the_page_does_not_open_a_chapter() -> None:
    """A pull quote or a figure label is large but is not where a chapter starts."""
    found = chapters_of(
        opener(Text("01 කාර්මික විප්ලවය", size=27, y=740)),
        Page(blocks=(*BODY, Text("විශාල උපුටා දැක්වීම", size=27, y=200))),
        opener(Text("02 ජාතික පුනරුදය", size=27, y=740)),
    )

    assert [chapter.page_index for chapter in found] == [0, 2]


def test_a_title_without_a_number_keeps_no_number() -> None:
    found = chapters_of(
        opener(Text("පෙරවදන", size=27, y=740)),
        opener(Text("ජාතික පුනරුදය", size=27, y=740)),
    )

    assert found[0] == Chapter(title="පෙරවදන", page_index=0, number=None)


def test_a_book_with_uniform_type_has_no_chapters() -> None:
    """No chapters are invented from page ranges."""
    assert chapters_of(*[sinhala_page()] * 6) == ()


def test_a_single_opener_is_not_a_chapter_list() -> None:
    """More often the document's own title than a chapter, and it navigates nowhere."""
    assert chapters_of(opener(Text("ලිපියේ මාතෘකාව", size=27, y=740)), sinhala_page()) == ()


def test_a_prepared_document_carries_its_chapters() -> None:
    prepared = prepare_document(
        build_pdf(
            [
                opener(Text("01 කාර්මික විප්ලවය", size=27, y=740)),
                opener(Text("02 ජාතික පුනරුදය", size=27, y=740)),
            ]
        )
    )

    assert prepared.chapters is not None
    assert [chapter.number for chapter in prepared.chapters] == ["01", "02"]


def test_a_prepared_document_without_chapters_says_none_rather_than_unknown() -> None:
    assert prepare_document(build_pdf([sinhala_page()])).chapters == ()
