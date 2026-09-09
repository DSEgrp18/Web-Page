"""Printed page numbers.

A reader who asks for page 42, or who is told an answer came from page 42, means
the number printed on the page. In a book with roman-numbered front matter that
is not the file position, and getting it wrong sends them somewhere else.
"""

from __future__ import annotations

import pytest
from pdf_fixtures import Page, build_pdf

from sinhala_documents import extract_document
from sinhala_documents.page_labels import _letters, _roman, page_labels


def labels_of(count: int, declared: list[tuple[int, str]] | None) -> list[str | None]:
    document = extract_document(build_pdf([Page()] * count, labels=declared))
    return [page.page_label for page in document.pages]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, "i"), (4, "iv"), (9, "ix"), (14, "xiv"), (40, "xl"), (1994, "mcmxciv")],
)
def test_roman_numerals_use_the_subtractive_forms(value: int, expected: str) -> None:
    assert _roman(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, "a"), (26, "z"), (27, "aa"), (52, "zz"), (53, "aaa")],
)
def test_letter_labels_repeat_as_the_specification_requires(value: int, expected: str) -> None:
    """A, B ... Z, AA, BB — not the AA, AB of a spreadsheet column."""
    assert _letters(value) == expected


def test_front_matter_is_numbered_separately_from_the_body() -> None:
    """The shape of nearly every real book."""
    assert labels_of(6, [(0, "r"), (3, "D")]) == ["i", "ii", "iii", "1", "2", "3"]


def test_numbering_continues_until_the_next_declared_change() -> None:
    assert labels_of(4, [(0, "D")]) == ["1", "2", "3", "4"]


def test_uppercase_and_lowercase_styles_are_distinct() -> None:
    assert labels_of(2, [(0, "R")]) == ["I", "II"]
    assert labels_of(2, [(0, "A")]) == ["A", "B"]


def test_a_pdf_without_page_labels_reports_none_rather_than_guessing() -> None:
    """Inventing "1, 2, 3" would be indistinguishable from a real declaration."""
    assert labels_of(3, None) == [None, None, None]


def test_a_broken_label_tree_costs_the_labels_and_nothing_else() -> None:
    """A malformed numbering tree is not a reason to refuse someone their book."""

    class Broken:
        @property
        def catalog(self) -> dict:
            raise ValueError("malformed")

    assert page_labels(Broken(), 3) == [None, None, None]
