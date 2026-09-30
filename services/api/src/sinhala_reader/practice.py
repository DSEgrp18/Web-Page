"""Building a quiz's questions, shared by the API and the worker.

Fill-in-the-blank runs in the request. Model drafting runs only in the Celery
worker (:func:`draft_quiz`), which imports the graph lazily: the API process
never loads ``langgraph`` (CLAUDE.md, "The agentic boundary").
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any

from sinhala_documents.model import QualityState
from sinhala_documents.passages import build_passages
from sinhala_documents.quiz import (
    CLOZE_VERSION,
    VERIFIER_VERSION,
    Candidate,
    Sentence,
    SourcePassage,
    cloze_questions,
    verify,
)
from sinhala_documents.retrieval import LexicalIndex, tokenize

from .storage import PageDecision, QuizStatus, Reading, Store

log = logging.getLogger(__name__)

#: ``graph`` adds model-drafted questions, run on the queue. Off by default:
#: sending a reader's book to a model is external processing.
QUIZ_ENV = "SINHALA_READER_QUIZ"

QUESTIONS_PER_QUIZ = 10

#: Only prose grounds a question: a heading, caption or contents row blanked
#: out is a question about layout, not about the book.
_PROSE = {"paragraph", "list_item", "unknown"}


def offered_generators() -> list[str]:
    """``graph`` only where it is switched on *and* its framework is installed.

    ``find_spec`` looks for the package without importing it, so the API
    process still never loads ``langgraph``. Offering a generator the image
    cannot run would leave a reader's quiz drafting forever.
    """
    wanted = os.environ.get(QUIZ_ENV, "").strip() == "graph"
    installed = importlib.util.find_spec("langgraph") is not None
    return ["cloze", "graph"] if wanted and installed else ["cloze"]


def quiz_mode() -> str:
    """Where practice questions can be drafted, for ``/readiness`` and the
    privacy notice: ``gemini`` when a reader may send passages to Google."""
    return "gemini" if "graph" in offered_generators() else "local"


KINDS = ("mixed", "facts", "causes", "terms")

#: The longest topic a reader may type. It is sent to the model when drafting,
#: so it is kept to a line.
MAX_TOPIC = 200


@dataclass(frozen=True)
class QuizRequest:
    """What the reader asked for: which part of the book, about what, and how
    many. Recorded in the quiz's provenance, so the worker reads it from there
    and a quiz can always say what it was made from."""

    first_page: int | None = None
    """Zero-based, inclusive. ``None`` means from the start."""
    last_page: int | None = None
    """Zero-based, inclusive. ``None`` means to the end."""
    topic: str = ""
    kind: str = "mixed"
    count: int = QUESTIONS_PER_QUIZ

    def __post_init__(self) -> None:
        # One line of plain text: angle brackets would let a topic close the
        # fence the model is told to treat as the reader's words.
        clean = re.sub(r"\s+", " ", re.sub(r"[<>]", " ", self.topic)).strip()[:MAX_TOPIC]
        object.__setattr__(self, "topic", clean)
        if self.kind not in KINDS:
            object.__setattr__(self, "kind", "mixed")

    def covers(self, page_index: int) -> bool:
        return (self.first_page is None or page_index >= self.first_page) and (
            self.last_page is None or page_index <= self.last_page
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_provenance(cls, provenance: str) -> QuizRequest:
        stored = json.loads(provenance or "{}").get("request") or {}
        fields = {
            k: stored[k]
            for k in ("first_page", "last_page", "topic", "kind", "count")
            if k in stored
        }
        return cls(**fields)


def question_sources(
    store: Store, reading: Reading
) -> tuple[list[SourcePassage], list[Sentence], LexicalIndex] | None:
    """The numbered passages a generator may use, and their prose sentences.

    A page grounds a question only if it was read cleanly, or a teacher
    accepted it on review. Withheld pages are already empty for a class.
    """
    from .routes.common import prepared_for_in

    # prepared_for_in reads only the store; the worker has no other deps.
    prepared = prepared_for_in(SimpleNamespace(store=store), reading, required=False)  # type: ignore[arg-type]
    document = reading.document
    if prepared is None or document.version is None:
        return None
    reviewed = store.page_reviews(document.document_id, document.owner, document.version)
    accepted = {
        page.page_index
        for page in prepared.pages
        if page.quality == QualityState.ACCEPTED
        or reviewed.get(page.page_index) == PageDecision.ACCEPTED
    }
    segments = {s.segment_id: s for page in prepared.pages for s in page.segments}
    passages = build_passages(prepared)
    numbered = [
        SourcePassage(
            number=number,
            text=passage.text,
            page_index=passage.page_index,
            page_label=passage.page_label,
            segment_ids=passage.segment_ids,
            accepted=passage.page_index in accepted,
        )
        for number, passage in enumerate(passages, start=1)
    ]
    sentences = [
        Sentence(passage=source.number, segment_id=sid, text=segments[sid].display_text)
        for source in numbered
        if source.accepted
        for sid in source.segment_ids
        if sid in segments and str(segments[sid].role) in _PROSE
    ]
    return numbered, sentences, LexicalIndex(passages)


@dataclass(frozen=True)
class Scoped:
    """The sources narrowed to what a reader asked for."""

    sentences: list[Sentence]
    """Prose sentences on the chosen pages."""
    first: list[int]
    """Positions in ``sentences`` matching the topic, best first."""
    passages: set[int]
    """Numbers of the passages on the chosen pages."""
    topic_passages: list[int]
    """Numbers of those passages matching the topic, best first."""
    lesson_terms: list[str]
    """The chosen part's key terms: what wrong options can be built from."""
    occurrences: Counter[str]
    """Every word's count across the whole book."""


def scoped(
    numbered: list[SourcePassage],
    sentences: list[Sentence],
    index: LexicalIndex,
    request: QuizRequest,
) -> Scoped:
    """Narrow a book's sources to the pages and topic a reader asked for."""
    in_scope = {p.number for p in numbered if request.covers(p.page_index)}
    chosen = [s for s in sentences if s.passage in in_scope]
    occurrences = Counter(token for s in sentences for token in tokenize(s.text))
    topic_passages: list[int] = []
    if request.topic:
        by_text = {p.text: p.number for p in numbered}
        for hit in index.search(request.topic, limit=len(numbered) or 1):
            number = by_text.get(hit.passage.text)
            if number in in_scope and number not in topic_passages:
                topic_passages.append(number)
    rank = {number: position for position, number in enumerate(topic_passages)}
    first = sorted(
        (i for i, s in enumerate(chosen) if s.passage in rank),
        key=lambda i: rank[chosen[i].passage],
    )
    terms = Counter(
        token
        for s in chosen
        for token in tokenize(s.text)
        if len(token) >= 4 and occurrences[token] >= 2 and index.is_informative(token)
    )
    lesson_terms = [
        term for term, _ in sorted(terms.items(), key=lambda kv: (-kv[1] * index.idf(kv[0]), kv[0]))
    ]
    return Scoped(chosen, first, in_scope, topic_passages, lesson_terms, occurrences)


def _stored(candidate: Candidate, source: SourcePassage, version: str) -> dict[str, Any]:
    segment = candidate.segment_id or next((sid for sid in source.segment_ids), None)
    return {
        "question_id": hashlib.sha256(
            f"{version}|{candidate.passage}|{candidate.question}".encode()
        ).hexdigest()[:12],
        "question": candidate.question,
        "options": list(candidate.options),
        "answer": candidate.answer,
        "quote": candidate.quote,
        "page_index": source.page_index,
        "page_label": source.page_label,
        "segment_id": segment,
    }


def keep_verified(
    candidates: list[Candidate], passages: list[SourcePassage], version: str
) -> list[dict[str, Any]]:
    """The candidates that pass the verifier, ready to store. The rest are gone."""
    by_number = {p.number: p for p in passages}
    return [
        _stored(c, by_number[c.passage], version)
        for c in candidates
        if verify(c, by_number) is None
    ]


def cloze_quiz(
    store: Store, reading: Reading, seed: str, request: QuizRequest | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Fill-in-the-blank questions and their provenance, made in the request."""
    request = request or QuizRequest()
    found = question_sources(store, reading)
    version = reading.document.version or ""
    kept: list[dict[str, Any]] = []
    if found is not None:
        numbered, sentences, index = found
        part = scoped(numbered, sentences, index, request)
        kept = keep_verified(
            cloze_questions(
                part.sentences,
                index,
                seed=seed,
                limit=request.count,
                first=part.first,
                occurrences=part.occurrences,
            ),
            numbered,
            version,
        )
    return kept, provenance("cloze", generator_version=CLOZE_VERSION, request=request.as_dict())


def provenance(generator: str, **fields: Any) -> str:
    return json.dumps(
        {
            "generator": generator,
            "generator_version": None,
            "verifier_version": VERIFIER_VERSION,
            "provider": None,
            "model": None,
            "prompt_version": None,
            "framework": None,
            **fields,
        }
    )


def draft_quiz(store: Store, quiz_id: str, transport: Any = None) -> None:
    """The worker's half: draft questions with the model, keep the verified ones.

    A provider failure fails the quiz and says so. It never quietly becomes a
    fill-in-the-blank quiz: the reader chooses that, knowing.
    """
    from sinhala_documents import quiz_graph

    quiz = store.quiz_for_worker(quiz_id)
    if quiz is None or quiz.status != QuizStatus.GENERATING:
        return  # Deleted, or already done: a redelivery does nothing.
    request = QuizRequest.from_provenance(quiz.provenance)
    reading = store.readable_document(quiz.document_id, quiz.creator)
    found = question_sources(store, reading) if reading is not None else None
    finished = QuizStatus.DRAFT if quiz.for_class else QuizStatus.PUBLISHED

    def fail(reason: str) -> None:
        log.info("quiz %s: drafting failed: %s", quiz_id, reason)
        store.update_quiz(
            quiz_id,
            quiz.creator,
            status=QuizStatus.FAILED,
            questions="[]",
            provenance=provenance("graph", failure=reason, request=request.as_dict()),
        )

    try:
        send = transport or quiz_graph.gemini_transport()
        if found is None:
            raise quiz_graph.ProviderFailure("The book is no longer available.")
        numbered, sentences, index = found
        part = scoped(numbered, sentences, index, request)
        result = quiz_graph.draft_questions(
            numbered,
            send,
            target=request.count,
            kind=request.kind,
            topic=request.topic,
            scope=part.passages,
            first=part.topic_passages,
            lesson_terms=part.lesson_terms,
        )
    except quiz_graph.ProviderFailure as failure:
        fail(str(failure))
        return
    except ImportError:
        # The image lacks the framework: fail the quiz and say so, rather than
        # leave it drafting forever.
        fail("The question drafter is not installed on this server.")
        return
    kept = keep_verified(result.accepted, numbered, quiz.version)
    store.update_quiz(
        quiz_id,
        quiz.creator,
        status=finished if kept else QuizStatus.FAILED,
        questions=json.dumps(kept, ensure_ascii=False),
        provenance=provenance(
            "graph",
            generator_version=quiz_graph.PROMPT_VERSION,
            provider="gemini",
            model=getattr(send, "model", None),
            prompt_version=quiz_graph.PROMPT_VERSION,
            framework=quiz_graph.framework_version(),
            calls=result.calls,
            stopped=result.stopped,
            rejections=result.rejections,
            request=request.as_dict(),
        ),
    )
