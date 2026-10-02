"""Character n-gram vectors: the dense arm without an external embedding model.

CLAUDE.md asks for lexical, dense and hybrid retrieval to be compared. This is
not a multilingual embedding claim — it is a deterministic baseline that can
partially bridge inflection gaps lexical search misses, measured on the same
held-out questions as BM25.
"""

from __future__ import annotations

import math
from collections import Counter

from .passages import Passage
from .retrieval import COMMON_TERM_FRACTION, Hit, tokenize

_NGRAM = 3


def _ngrams(text: str) -> list[str]:
    compact = "".join(text.split())
    if len(compact) < _NGRAM:
        return [compact] if compact else []
    return [compact[i : i + _NGRAM] for i in range(len(compact) - _NGRAM + 1)]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class DenseIndex:
    """Cosine similarity over character n-gram tf-idf vectors, one document only."""

    def __init__(self, passages: tuple[Passage, ...] | list[Passage]) -> None:
        self._passages = tuple(passages)
        self._grams = [Counter(_ngrams(p.text)) for p in self._passages]
        documents = Counter()
        for grams in self._grams:
            documents.update(set(grams))
        total = len(self._passages)
        self._idf = {
            gram: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for gram, count in documents.items()
        }
        ceiling = max(1, int(total * COMMON_TERM_FRACTION))
        self._informative = {gram for gram, count in documents.items() if count <= ceiling}
        self._weighted = [
            Counter({g: c * self._idf.get(g, 0.0) for g, c in grams.items()})
            for grams in self._grams
        ]

    @property
    def document_version(self) -> str | None:
        return self._passages[0].document_version if self._passages else None

    def search(self, question: str, *, limit: int = 5) -> tuple[Hit, ...]:
        query = Counter(_ngrams(question))
        if not query or not self._passages:
            return ()
        weighted_query = Counter({g: c * self._idf.get(g, 0.0) for g, c in query.items()})
        hits: list[Hit] = []
        for index, passage in enumerate(self._passages):
            score = _cosine(weighted_query, self._weighted[index])
            if score <= 0:
                continue
            matched_tokens = tuple(
                t for t in set(tokenize(question)) if t in tokenize(passage.text)
            )
            informative = any(g in self._informative for g in query if g in self._grams[index])
            if not informative and not matched_tokens:
                continue
            terms = matched_tokens or tuple(query.keys())[:3]
            hits.append(Hit(passage=passage, score=score, terms=terms))
        hits.sort(key=lambda hit: (-hit.score, hit.passage.page_index))
        return tuple(hits[:limit])


class HybridIndex:
    """Reciprocal rank fusion of lexical BM25 and character n-gram dense search."""

    def __init__(self, passages: tuple[Passage, ...] | list[Passage]) -> None:
        from .retrieval import LexicalIndex

        self._lexical = LexicalIndex(passages)
        self._dense = DenseIndex(passages)
        self._passages = tuple(passages)

    @property
    def document_version(self) -> str | None:
        return self._passages[0].document_version if self._passages else None

    def search(self, question: str, *, limit: int = 5) -> tuple[Hit, ...]:
        lexical = self._lexical.search(question, limit=limit * 2)
        dense = self._dense.search(question, limit=limit * 2)
        scores: dict[str, float] = {}
        terms: dict[str, tuple[str, ...]] = {}
        for rank, hit in enumerate(lexical):
            scores[hit.passage.passage_id] = scores.get(hit.passage.passage_id, 0.0) + 1.0 / (
                60 + rank + 1
            )
            terms[hit.passage.passage_id] = hit.terms
        for rank, hit in enumerate(dense):
            scores[hit.passage.passage_id] = scores.get(hit.passage.passage_id, 0.0) + 1.0 / (
                60 + rank + 1
            )
            terms.setdefault(hit.passage.passage_id, hit.terms)
        ordered = sorted(
            scores.items(),
            key=lambda item: (
                -item[1],
                next(p.page_index for p in self._passages if p.passage_id == item[0]),
            ),
        )
        by_id = {p.passage_id: p for p in self._passages}
        hits = [
            Hit(passage=by_id[pid], score=score, terms=terms.get(pid, ()))
            for pid, score in ordered[:limit]
            if pid in by_id
        ]
        return tuple(hits)
