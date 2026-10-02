"""Answer metrics on a held-out question file: citation support, correctness, abstention.

Each CSV row has ``question``, ``book`` (under ``evaluation/data/``), ``pages`` (gold
page indexes, ``;``-separated, or empty when the book cannot answer), and
``acceptable`` (optional substring that must appear in a non-abstaining answer).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sinhala_documents.answerer import answer_question
from sinhala_documents.retrieval_select import MODES

from .books import passages, prepare
from .stats import bootstrap


@dataclass(frozen=True)
class AnswerQuestion:
    question: str
    book: str
    pages: frozenset[int]
    acceptable: str | None

    @property
    def answerable(self) -> bool:
        return bool(self.pages)


def read_answer_questions(path: Path) -> list[AnswerQuestion]:
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    out: list[AnswerQuestion] = []
    for row in rows:
        pages_raw = row.get("pages", "").strip()
        pages = frozenset(int(p) for p in pages_raw.split(";") if p.strip())
        acceptable = (row.get("acceptable") or "").strip() or None
        out.append(
            AnswerQuestion(
                question=row["question"].strip(),
                book=row["book"].strip(),
                pages=pages,
                acceptable=acceptable,
            )
        )
    return out


def _citation_supported(result, gold: frozenset[int]) -> bool:
    if result.abstained or not result.citations:
        return False
    return any(c.page_index in gold for c in result.citations)


def _correct(result, acceptable: str | None) -> bool:
    if result.abstained or not result.answer:
        return False
    if acceptable is None:
        return True
    return acceptable in result.answer


def evaluate(questions: list[AnswerQuestion], root: Path, *, mode: str = "lexical") -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    prepared: dict[str, tuple] = {}
    citation_hits: list[float] = []
    correct_hits: list[float] = []
    abstained_ok: list[float] = []
    for question in questions:
        if question.book not in prepared:
            prepared[question.book] = passages(prepare(root / question.book))
        passage_list = prepared[question.book]
        result = answer_question(question.question, passage_list, mode=mode)
        if question.answerable:
            citation_hits.append(1.0 if _citation_supported(result, question.pages) else 0.0)
            correct_hits.append(1.0 if _correct(result, question.acceptable) else 0.0)
        else:
            abstained_ok.append(1.0 if result.abstained else 0.0)
    return {
        "mode": mode,
        "citation_supported": bootstrap(citation_hits).as_dict() if citation_hits else {},
        "answer_correct": bootstrap(correct_hits).as_dict() if correct_hits else {},
        "abstention_correct": bootstrap(abstained_ok).as_dict() if abstained_ok else {},
        "answerable": len(citation_hits),
        "unanswerable": len(abstained_ok),
        "books": len(prepared),
    }
