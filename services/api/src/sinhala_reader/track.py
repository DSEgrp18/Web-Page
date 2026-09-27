"""What a reader has heard, how they answered, and what is due for review.

Framework free, so the rules are tested on their own: the bitmap of heard
sentences, the Leitner schedule, and the per-chapter rows the progress page
and the teacher's view are both built from.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

#: Sri Lanka's clock. A fixed offset rather than a zone database: it has had no
#: daylight saving since 2006, and Windows Python ships no tz data.
COLOMBO = timezone(timedelta(hours=5, minutes=30))

#: Days until a question comes back, by Leitner box 1 to 5.
INTERVALS = (1, 2, 4, 8, 16)


def today(now: datetime | None = None) -> str:
    """The date in Colombo, ``YYYY-MM-DD``. Reviews fall due by the student's day."""
    return (now or datetime.now(COLOMBO)).astimezone(COLOMBO).date().isoformat()


def schedule(previous: tuple[int, str] | None, correct: bool, on: str) -> tuple[int, str]:
    """The box and due date after an answer given on ``on``.

    ``previous`` is the last answer's (box, due_on). A wrong answer goes back
    to box 1. A right one moves up a box, but only when the question was due:
    answering again the same afternoon is not spacing, so it changes nothing.
    """
    day = date.fromisoformat(on)
    if not correct:
        return 1, (day + timedelta(days=INTERVALS[0])).isoformat()
    if previous is not None and previous[1] > on:
        return previous
    box = 1 if previous is None else min(previous[0] + 1, len(INTERVALS))
    return box, (day + timedelta(days=INTERVALS[box - 1])).isoformat()


def is_due(due_on: str, on: str) -> bool:
    """Answers recorded before scheduling existed have no date, and are due."""
    return due_on <= on


def set_bits(bits: bytes, indices: Iterable[int]) -> bytes:
    """``bits`` with each index turned on, grown as needed."""
    out = bytearray(bits)
    for index in indices:
        if index < 0:
            continue
        byte, bit = divmod(index, 8)
        if byte >= len(out):
            out.extend(b"\0" * (byte + 1 - len(out)))
        out[byte] |= 1 << bit
    return bytes(out)


def is_set(bits: bytes, index: int) -> bool:
    byte, bit = divmod(index, 8)
    return byte < len(bits) and bool(bits[byte] >> bit & 1)


@dataclass(frozen=True)
class Answered:
    """One of the reader's answers, placed in the book by its question's page."""

    page_index: int
    correct: bool
    due: bool


@dataclass(frozen=True)
class ChapterRow:
    """One row of the progress table. ``title`` is ``None`` for a whole book
    without detected chapters, or for the pages before the first chapter."""

    title: str | None
    first_page: int
    sentences: int
    heard: int
    answered: int
    correct: int
    due: int

    @property
    def complete(self) -> bool:
        return self.sentences > 0 and self.heard == self.sentences


def chapter_rows(
    segments: Sequence[tuple[int, int]],
    chapters: Sequence[tuple[str, int]] | None,
    bits: bytes,
    answers: Sequence[Answered],
) -> list[ChapterRow]:
    """One row per chapter: what was heard of it, and how its questions went.

    ``segments`` are (index, page_index) in reading order; ``chapters`` are
    (title, opening page_index). A chapter runs to the page before the next one
    opens. Pages before the first chapter get an untitled row, if they hold
    anything to hear or ask about.
    """
    opens = sorted(chapters or [], key=lambda c: c[1])
    starts: list[tuple[str | None, int]] = [(title, page) for title, page in opens]
    if not starts or starts[0][1] > 0:
        starts.insert(0, (None, 0))

    def row_of(page_index: int) -> int:
        found = 0
        for position, (_, first) in enumerate(starts):
            if first <= page_index:
                found = position
        return found

    tally = [[0, 0, 0, 0, 0] for _ in starts]
    for index, page_index in segments:
        counts = tally[row_of(page_index)]
        counts[0] += 1
        counts[1] += is_set(bits, index)
    for answer in answers:
        counts = tally[row_of(answer.page_index)]
        counts[2] += 1
        counts[3] += answer.correct
        counts[4] += answer.due
    rows = [
        ChapterRow(title, first, *counts)
        for (title, first), counts in zip(starts, tally, strict=True)
    ]
    # An untitled opening with nothing in it is not a chapter anyone missed.
    return [r for r in rows if r.title is not None or r.sentences or r.answered]
