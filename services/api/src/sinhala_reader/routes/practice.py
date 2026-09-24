"""Practice questions on a book: made, reviewed, taken.

Every question has passed the deterministic verifier in
``sinhala_documents.quiz`` before it is stored, and a failed check discarded it
(CLAUDE.md, "Generated questions"). A quiz records which generator made it and
the verifier's version.

* Anyone who may read a book may make a **personal** quiz on it, usable at once
  and seen by nobody else.
* The book's owner, if a teacher, may make a **class** quiz. It is a draft
  until they publish it, which is their approval of every question they left
  in; until then no student sees it.
* A quiz belongs to the version it was made from, and says it is **stale** once
  the reader's version of the book has moved on.

Access is decided in the store (``Store.quiz_for``). Anything a reader may not
see is absent (404).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sinhala_documents.model import QualityState
from sinhala_documents.passages import build_passages
from sinhala_documents.quiz import (
    CLOZE_VERSION,
    VERIFIER_VERSION,
    Sentence,
    SourcePassage,
    cloze_questions,
    verify,
)
from sinhala_documents.retrieval import LexicalIndex

from ..ratelimit import enforce
from ..security import require_owner
from ..storage import (
    AuditEvent,
    PageDecision,
    Quiz,
    QuizAnswer,
    QuizStatus,
    Reading,
    Role,
    new_id,
)
from .common import prepared_for_in, readable_in

if TYPE_CHECKING:
    from ..app import Deps

#: Which generators this deployment offers. ``graph`` drafts questions with a
#: model, in the worker; it is never switched to, or from, silently.
QUIZ_ENV = "SINHALA_READER_QUIZ"

#: Questions per quiz. A short set is one a student finishes.
QUESTIONS_PER_QUIZ = 10

#: Only prose grounds a question: a heading, caption or contents row blanked
#: out is a question about layout, not about the book.
_PROSE = {"paragraph", "list_item", "unknown"}

NO_QUIZ = "No such quiz."


class NewQuiz(BaseModel):
    generator: str = Field(default="cloze", pattern="^(cloze|graph)$")
    for_class: bool = False


class QuestionView(BaseModel):
    question_id: str
    question: str
    options: list[str]
    page_label: str | None
    answer: int | None = Field(
        default=None, description="Only for the quiz's maker, who has to review it."
    )


class MyAnswer(BaseModel):
    question_id: str
    choice: int
    correct: bool


class QuizSummary(BaseModel):
    quiz_id: str
    document_id: str
    for_class: bool
    status: str
    generator: str
    question_count: int
    stale: bool
    mine: bool
    created_at: str


class QuizDetail(QuizSummary):
    questions: list[QuestionView]
    answers: list[MyAnswer]


class AnswerBody(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    choice: int = Field(ge=0, le=9)


class AnswerResult(BaseModel):
    correct: bool
    answer: int
    quote: str = Field(description="The book's own sentence the question came from.")
    page_index: int
    page_label: str | None
    segment_id: str | None


def register(app: FastAPI, deps: Deps) -> None:
    """Add the practice routes to ``app``, acting through ``deps``."""
    store = deps.store

    def offered() -> set[str]:
        return {"cloze", *(["graph"] if os.environ.get(QUIZ_ENV) == "graph" else [])}

    def current_version(quiz: Quiz, reader: str) -> str | None:
        reading = store.readable_document(quiz.document_id, reader)
        return reading.document.version if reading else None

    def summary(quiz: Quiz, reader: str) -> QuizSummary:
        provenance = json.loads(quiz.provenance)
        return QuizSummary(
            quiz_id=quiz.quiz_id,
            document_id=quiz.document_id,
            for_class=quiz.for_class,
            status=str(quiz.status),
            generator=provenance.get("generator", "cloze"),
            question_count=len(json.loads(quiz.questions)),
            stale=current_version(quiz, reader) != quiz.version,
            mine=quiz.creator == reader,
            created_at=quiz.created_at,
        )

    def detail(quiz: Quiz, reader: str) -> QuizDetail:
        mine = quiz.creator == reader
        questions = [
            QuestionView(
                question_id=q["question_id"],
                question=q["question"],
                options=q["options"],
                page_label=q["page_label"],
                answer=q["answer"] if mine else None,
            )
            for q in json.loads(quiz.questions)
        ]
        answers = [
            MyAnswer(question_id=a.question_id, choice=a.choice, correct=a.correct)
            for a in store.quiz_answers(quiz.quiz_id, reader)
        ]
        return QuizDetail(
            **summary(quiz, reader).model_dump(), questions=questions, answers=answers
        )

    def visible(quiz_id: str, reader: str) -> Quiz:
        quiz = store.quiz_for(quiz_id, reader)
        if quiz is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_QUIZ)
        return quiz

    def sources(reading: Reading) -> tuple[list[SourcePassage], list[Sentence], LexicalIndex]:
        """The numbered passages a generator may use, and their prose sentences.

        A page grounds a question only if it was read cleanly, or a teacher
        accepted it on review. Withheld pages are already empty for a class.
        """
        prepared = prepared_for_in(deps, reading)
        assert prepared is not None
        document = reading.document
        assert document.version is not None
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

    @app.post(
        "/documents/{document_id}/quizzes",
        status_code=status.HTTP_201_CREATED,
        tags=["practice"],
    )
    def make_quiz(
        document_id: str, body: NewQuiz, request: Request, reader: str = Depends(require_owner)
    ) -> QuizDetail:
        """Make practice questions from the book, each checked by the verifier.

        ``graph`` is offered only where this deployment configured it, and is
        refused otherwise rather than quietly replaced by fill-in-the-blank.
        """
        reading = readable_in(deps, document_id, reader)
        if body.generator not in offered():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "generator_unavailable", "message": "That kind of question is off here."},
            )
        if body.for_class:
            user = store.get_user(reader)
            if not reading.as_owner or user is None or user.role != Role.TEACHER:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "Only the book's teacher can make a class quiz."
                )
        enforce(request, "quiz", reader)
        numbered, sentences, index = sources(reading)
        version = reading.document.version
        assert version is not None
        by_number = {source.number: source for source in numbered}
        candidates = cloze_questions(
            sentences, index, seed=f"{version}|{reader}|{new_id('q')}", limit=QUESTIONS_PER_QUIZ
        )
        kept = []
        for candidate in candidates:
            if verify(candidate, by_number) is not None:
                continue  # Discarded, never repaired.
            source = by_number[candidate.passage]
            kept.append(
                {
                    "question_id": hashlib.sha256(
                        f"{version}|{candidate.segment_id}|{candidate.question}".encode()
                    ).hexdigest()[:12],
                    "question": candidate.question,
                    "options": list(candidate.options),
                    "answer": candidate.answer,
                    "quote": candidate.quote,
                    "page_index": source.page_index,
                    "page_label": source.page_label,
                    "segment_id": candidate.segment_id,
                }
            )
        if not kept:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "no_questions", "message": "No questions could be made from this book."},
            )
        quiz = store.put_quiz(
            Quiz(
                quiz_id=new_id("quiz"),
                document_id=document_id,
                creator=reader,
                version=version,
                for_class=body.for_class,
                status=QuizStatus.DRAFT if body.for_class else QuizStatus.PUBLISHED,
                provenance=json.dumps(
                    {
                        "generator": "cloze",
                        "generator_version": CLOZE_VERSION,
                        "verifier_version": VERIFIER_VERSION,
                        "provider": None,
                        "model": None,
                        "prompt_version": None,
                        "framework": None,
                    }
                ),
                questions=json.dumps(kept, ensure_ascii=False),
            )
        )
        return detail(quiz, reader)

    @app.get("/documents/{document_id}/quizzes", tags=["practice"])
    def list_quizzes(document_id: str, reader: str = Depends(require_owner)) -> list[QuizSummary]:
        """The reader's own quizzes on this book, and their class's published ones."""
        readable_in(deps, document_id, reader)
        return [summary(quiz, reader) for quiz in store.quizzes_for(document_id, reader)]

    @app.get("/quizzes/{quiz_id}", tags=["practice"])
    def get_quiz(quiz_id: str, reader: str = Depends(require_owner)) -> QuizDetail:
        return detail(visible(quiz_id, reader), reader)

    @app.post("/quizzes/{quiz_id}/answers", tags=["practice"])
    def answer(
        quiz_id: str, body: AnswerBody, reader: str = Depends(require_owner)
    ) -> AnswerResult:
        """Check one answer, record it as this reader's, and say where it came from."""
        quiz = visible(quiz_id, reader)
        question = next(
            (q for q in json.loads(quiz.questions) if q["question_id"] == body.question_id), None
        )
        if question is None or body.choice >= len(question["options"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.")
        correct = body.choice == question["answer"]
        store.put_quiz_answer(
            QuizAnswer(
                quiz_id=quiz_id,
                user_id=reader,
                question_id=body.question_id,
                choice=body.choice,
                correct=correct,
            )
        )
        return AnswerResult(
            correct=correct,
            answer=question["answer"],
            quote=question["quote"],
            page_index=question["page_index"],
            page_label=question["page_label"],
            segment_id=question["segment_id"],
        )

    def drafted(quiz_id: str, reader: str) -> Quiz:
        quiz = visible(quiz_id, reader)
        if quiz.creator != reader:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_QUIZ)
        if quiz.status != QuizStatus.DRAFT:
            raise HTTPException(status.HTTP_409_CONFLICT, "This quiz is already published.")
        return quiz

    @app.delete("/quizzes/{quiz_id}/questions/{question_id}", tags=["practice"])
    def drop_question(
        quiz_id: str, question_id: str, reader: str = Depends(require_owner)
    ) -> QuizDetail:
        """Take a question out of a draft, in review. Never edited: only removed."""
        quiz = drafted(quiz_id, reader)
        questions = [q for q in json.loads(quiz.questions) if q["question_id"] != question_id]
        updated = store.update_quiz(
            quiz_id, reader, status=quiz.status, questions=json.dumps(questions, ensure_ascii=False)
        )
        assert updated is not None
        return detail(updated, reader)

    @app.post("/quizzes/{quiz_id}/publish", tags=["practice"])
    def publish_quiz(quiz_id: str, reader: str = Depends(require_owner)) -> QuizDetail:
        """The teacher approves every question left in the draft, and the class sees it."""
        quiz = drafted(quiz_id, reader)
        if not json.loads(quiz.questions):
            raise HTTPException(status.HTTP_409_CONFLICT, "A quiz needs at least one question.")
        updated = store.update_quiz(
            quiz_id, reader, status=QuizStatus.PUBLISHED, questions=quiz.questions
        )
        assert updated is not None
        store.record(
            AuditEvent(
                event_id=new_id("aud"),
                kind="quiz_published",
                actor=reader,
                subject=reader,
                reason=f"quiz:{quiz_id}",
            )
        )
        return detail(updated, reader)

    @app.delete("/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["practice"])
    def delete_quiz(quiz_id: str, reader: str = Depends(require_owner)) -> Response:
        if not store.delete_quiz(quiz_id, reader):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_QUIZ)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
