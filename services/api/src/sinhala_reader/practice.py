"""Building a quiz's questions, shared by the API and the worker.

Fill-in-the-blank runs in the request. Model drafting runs only in the Celery
worker (:func:`draft_quiz`), which imports the graph lazily: the API process
never loads ``langgraph`` (CLAUDE.md, "The agentic boundary").
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
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
from sinhala_documents.retrieval import LexicalIndex

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
    return ["cloze", "graph"] if os.environ.get(QUIZ_ENV, "").strip() == "graph" else ["cloze"]


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


def cloze_quiz(store: Store, reading: Reading, seed: str) -> tuple[list[dict[str, Any]], str]:
    """Fill-in-the-blank questions and their provenance, made in the request."""
    found = question_sources(store, reading)
    version = reading.document.version or ""
    kept: list[dict[str, Any]] = []
    if found is not None:
        numbered, sentences, index = found
        kept = keep_verified(
            cloze_questions(sentences, index, seed=seed, limit=QUESTIONS_PER_QUIZ),
            numbered,
            version,
        )
    return kept, provenance("cloze", generator_version=CLOZE_VERSION)


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
    reading = store.readable_document(quiz.document_id, quiz.creator)
    found = question_sources(store, reading) if reading is not None else None
    finished = QuizStatus.DRAFT if quiz.for_class else QuizStatus.PUBLISHED
    try:
        send = transport or quiz_graph.gemini_transport()
        if found is None:
            raise quiz_graph.ProviderFailure("The book is no longer available.")
        numbered, _, _ = found
        result = quiz_graph.draft_questions(numbered, send)
    except quiz_graph.ProviderFailure as failure:
        log.info("quiz %s: drafting failed: %s", quiz_id, failure)
        store.update_quiz(
            quiz_id,
            quiz.creator,
            status=QuizStatus.FAILED,
            questions="[]",
            provenance=provenance("graph", failure=str(failure)),
        )
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
        ),
    )
