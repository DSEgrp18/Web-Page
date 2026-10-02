"""Retrieval Recall@5 on held-out questions, for the lexical retriever the
product uses.

A question file is a CSV with ``question``, ``book`` (a path under
``evaluation/data/``) and ``pages``: the zero-based page indexes that hold the
answer, separated by ``;``, or empty for a question the book cannot answer.
Answerable questions give Recall@k; unanswerable ones are counted, and left
for the abstention measure, which needs the answerer, not the retriever.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sinhala_documents.retrieval_select import MODES, build_index

from .books import passages, prepare
from .stats import bootstrap


@dataclass(frozen=True)
class Question:
    question: str
    book: str
    pages: frozenset[int]

    @property
    def answerable(self) -> bool:
        return bool(self.pages)


def read_questions(path: Path) -> list[Question]:
    with path.open(encoding="utf-8-sig") as handle:
        return [
            Question(
                question=row["question"].strip(),
                book=row["book"].strip(),
                pages=frozenset(int(p) for p in row["pages"].split(";") if p.strip()),
            )
            for row in csv.DictReader(handle)
        ]


def hit(retrieved_pages: list[int], gold: frozenset[int]) -> bool:
    """A question is recalled if any of its top passages is on a gold page."""
    return any(page in gold for page in retrieved_pages)


def recall_at(
    questions: list[Question], root: Path, *, k: int = 5, mode: str = "lexical"
) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    indexes: dict[str, object] = {}
    scores: list[float] = []
    for question in questions:
        if not question.answerable:
            continue
        if question.book not in indexes:
            indexes[question.book] = build_index(
                passages(prepare(root / question.book)), mode
            )
        hits = indexes[question.book].search(question.question, limit=k)
        scores.append(1.0 if hit([h.passage.page_index for h in hits], question.pages) else 0.0)
    return {
        f"recall_at_{k}": bootstrap(scores).as_dict(),
        "answerable": len(scores),
        "unanswerable": sum(not q.answerable for q in questions),
        "books": len(indexes),
        "retriever": mode,
    }


def compare_modes(questions: list[Question], root: Path, *, k: int = 5) -> dict:
    return {mode: recall_at(questions, root, k=k, mode=mode) for mode in MODES}
