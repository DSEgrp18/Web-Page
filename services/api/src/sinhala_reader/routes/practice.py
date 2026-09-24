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

import json
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..practice import cloze_quiz, offered_generators, provenance
from ..ratelimit import enforce
from ..security import require_owner
from ..storage import AuditEvent, Quiz, QuizAnswer, QuizStatus, Role, new_id
from .common import readable_in

if TYPE_CHECKING:
    from ..app import Deps

NO_QUIZ = "No such quiz."


class QuizGenerators(BaseModel):
    generators: list[str] = Field(description="cloze always; graph where configured.")


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
    status: str = Field(description="generating, failed, draft or published.")
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

    @app.get("/quiz-generators", tags=["practice"])
    def generators(reader: str = Depends(require_owner)) -> QuizGenerators:
        """Which kinds of question this deployment can make."""
        return QuizGenerators(generators=offered_generators())

    @app.post(
        "/documents/{document_id}/quizzes",
        status_code=status.HTTP_201_CREATED,
        tags=["practice"],
    )
    def make_quiz(
        document_id: str,
        body: NewQuiz,
        request: Request,
        response: Response,
        reader: str = Depends(require_owner),
    ) -> QuizDetail:
        """Make practice questions from the book, each checked by the verifier.

        ``cloze`` is made here and now. ``graph`` is drafted by a model in the
        worker: the quiz comes back ``generating`` (202) and is polled. It is
        offered only where configured, and refused otherwise rather than
        quietly replaced by fill-in-the-blank.
        """
        reading = readable_in(deps, document_id, reader)
        if body.generator not in offered_generators():
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
        version = reading.document.version
        assert version is not None
        quiz_id = new_id("quiz")
        if body.generator == "graph":
            quiz = store.put_quiz(
                Quiz(
                    quiz_id=quiz_id,
                    document_id=document_id,
                    creator=reader,
                    version=version,
                    for_class=body.for_class,
                    status=QuizStatus.GENERATING,
                    provenance=provenance("graph"),
                    questions="[]",
                )
            )
            assert deps.draft_quiz is not None
            deps.draft_quiz(quiz_id)
            response.status_code = status.HTTP_202_ACCEPTED
            return detail(store.quiz_for(quiz_id, reader) or quiz, reader)
        kept, made_by = cloze_quiz(store, reading, seed=f"{version}|{reader}|{quiz_id}")
        if not kept:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "no_questions", "message": "No questions could be made from this book."},
            )
        quiz = store.put_quiz(
            Quiz(
                quiz_id=quiz_id,
                document_id=document_id,
                creator=reader,
                version=version,
                for_class=body.for_class,
                status=QuizStatus.DRAFT if body.for_class else QuizStatus.PUBLISHED,
                provenance=made_by,
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
