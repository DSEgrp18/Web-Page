"""Where the book's chapters begin, read from its own typography.

A reader told to study "chapter 4" of a 168-page textbook cannot find it by
pressing "next page" thirty times, and cannot look at the contents page to
learn that it starts on page 61. A chapter list is the difference between a
book she can study and a book she can only play.

What a chapter is, here
-----------------------
A page that **opens** a chapter, recognised by how it is typeset: near the top
of the page, text set much larger than the book's body. On the Grade 11 history
textbook every chapter opener carries its number at 27 pt over a 12 pt body,
while the contents page tops out at 20 pt and section headings at 14 pt. That
gap is what the thresholds below are measured against, not guessed at.

The chapter's title is the book's own large text at the top of that page, in
reading order, with a standalone number ("02", or the "01" of
"01 කාර්මික විප්ලවය") separated out as the chapter's number. No word is
supplied, corrected or completed: CLAUDE.md forbids that of anything a reader
hears as the document, and a chapter title is read aloud like any other.

What this refuses to do
-----------------------
* **Invent chapters from page ranges.** "Chapter 3, page 30" on a book that has
  no chapter 3 at page 30 is confident nonsense a blind reader cannot check. A
  book whose typography yields nothing gets an empty list, and the interface
  says so.
* **Trust sizes it did not measure.** OCR'd lines carry a size estimated from
  pixel heights, so they are ignored, as is anything not accepted for reading.
* **Offer a list of one.** A single opener is more often the document's own
  title than a chapter, and a one-row list navigates nowhere.

This is deterministic structure and needs no provider. A PDF's own outline, and
headings from verified structure inference, are better sources where they
exist and are not used yet.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .model import DocumentExtraction, ExtractionMethod, QualityState, TextLine

#: Bumped when the rule below changes which pages count as chapter openers.
CHAPTERS_VERSION = "typography-1"

#: A line at least this many times the body size opens a chapter. The textbook
#: separates 27 pt chapter numbers from a 20 pt contents heading; 2x a 12 pt body
#: sits between them.
OPENER_RATIO = 2.0

#: Lines at least this large, near the top of an opener, form its title. Catches
#: the 20 pt title lines that sit either side of a 27 pt number.
TITLE_RATIO = 1.5

#: How far down the page an opener's title may start, as a fraction of height.
TOP_FRACTION = 0.25

_MEASURED = frozenset({ExtractionMethod.NATIVE, ExtractionMethod.LEGACY})
_NUMBER_ONLY = re.compile(r"^\s*(\d{1,3})[.)]?\s*$")
_LEADING_NUMBER = re.compile(r"^\s*(\d{1,3})[.)]?\s+(\S.*)$")


@dataclass(frozen=True)
class Chapter:
    """A chapter as the book prints it."""

    title: str
    """The book's own words. May be empty when the opener shows only a number."""

    page_index: int
    """Zero-based position in the file of the page the chapter opens on."""

    number: str | None = None
    """As printed, so "02" stays "02". ``None`` when the book prints none."""


def _measured(line: TextLine) -> bool:
    return line.quality is QualityState.ACCEPTED and line.methods <= _MEASURED


def _size(line: TextLine) -> float:
    return max(span.size for span in line.spans)


def body_size(extraction: DocumentExtraction) -> float | None:
    """The size most of the book's characters are set in."""
    sizes: Counter[float] = Counter()
    for page in extraction.pages:
        for line in page.lines:
            if not _measured(line):
                continue
            for span in line.spans:
                sizes[round(span.size, 1)] += len(span.text.strip())
    if not sizes:
        return None
    return sizes.most_common(1)[0][0]


def find_chapters(extraction: DocumentExtraction) -> tuple[Chapter, ...]:
    """The chapters, in the order the book presents them, or none at all."""
    body = body_size(extraction)
    if not body:
        return ()

    chapters: list[Chapter] = []
    for page in extraction.pages:
        top = [
            line
            for line in page.lines
            if _measured(line) and line.text.strip() and line.box.top <= page.height * TOP_FRACTION
        ]
        if not any(_size(line) >= body * OPENER_RATIO for line in top):
            continue

        number: str | None = None
        words: list[str] = []
        for line in top:
            if _size(line) < body * TITLE_RATIO:
                continue
            text = " ".join(line.text.split())
            if number is None and (alone := _NUMBER_ONLY.match(text)):
                number = alone.group(1)
                continue
            if number is None and not words and (leading := _LEADING_NUMBER.match(text)):
                number, text = leading.group(1), leading.group(2)
            words.append(text)
        chapters.append(Chapter(title=" ".join(words), page_index=page.page_index, number=number))

    return tuple(chapters) if len(chapters) >= 2 else ()
