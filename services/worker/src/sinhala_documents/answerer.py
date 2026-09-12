"""Grounded answers over retrieved passages.

Retrieval only says *which passages might matter*. It cannot tell whether a
match on a question-shaped word supports an answer, so this layer owns the
decision to abstain.

There is intentionally no generative model here. Until a Sinhala answer model
is evaluated for citation faithfulness, the safest useful answer is extractive:
return the book's own matching passage, alongside the exact segment ids a
reader can open or play. That makes every word in an answer attributable to the
private document that supplied it, rather than to an unreviewed model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .passages import Passage
from .retrieval import Hit, LexicalIndex

# Question scaffolding is not evidence. This intentionally small set is not a
# Sinhala stopword list (there is no evaluated one in this project); it simply
# stops an answer being issued when the only lexical overlap is an interrogative
# or connective in the question itself.
_QUESTION_SCAFFOLD = frozenset(
    {
        "ද",
        "ගැන",
        "කවුද",
        "කවදා",
        "කොහේ",
        "කෙසේද",
        "කුමක්",
        "කියන්න",
        "කරන්න",
        "පිළිබඳ",
        "වන්නේ",
        "ඇයි",
    }
)


@dataclass(frozen=True)
class Citation:
    """Evidence and a reachable place in the document."""

    passage_id: str
    page_index: int
    page_label: str | None
    section: str
    segment_ids: tuple[str, ...]
    quote: str


@dataclass(frozen=True)
class Answer:
    """An extractive answer, or an explicit lack of support."""

    answer: str | None
    citations: tuple[Citation, ...]
    abstained: bool


def answer_question(question: str, passages: tuple[Passage, ...] | list[Passage]) -> Answer:
    """Return only evidence the document actually supplies.

    A retrieval hit whose only terms are question scaffolding is not enough to
    answer. This errs toward abstention: a reader can ask a clearer question,
    whereas a confident answer from an unrelated passage is hard to detect
    without sight and harder to undo.
    """
    hits = LexicalIndex(passages).search(question, limit=3)
    supported = tuple(hit for hit in hits if _has_content_support(hit))
    if not supported:
        return Answer(answer=None, citations=(), abstained=True)

    citations = tuple(_citation(hit.passage) for hit in supported)
    # The primary passage is quoted exactly. It is not paraphrased, completed,
    # or combined with external knowledge; the citations below provide any
    # additional retrieved context without pretending it is one answer.
    return Answer(answer=supported[0].passage.text, citations=citations, abstained=False)


def _has_content_support(hit: Hit) -> bool:
    return any(term not in _QUESTION_SCAFFOLD for term in hit.terms)


def _citation(passage: Passage) -> Citation:
    return Citation(
        passage_id=passage.passage_id,
        page_index=passage.page_index,
        page_label=passage.page_label,
        section=passage.section,
        segment_ids=passage.segment_ids,
        quote=passage.text,
    )
