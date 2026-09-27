"""Track: what a reader has heard, how their answers went, and what is due.

* A reader reports sentences they listened to the end of; they are kept as a
  bitmap per book (``Store.mark_heard``).
* ``/progress`` is theirs alone: every book they may read, chapter by chapter,
  and the quizzes with questions due for review.
* A teacher sees a class's progress only from students who chose to share it,
  only on the books published to that class, and only answers to the class's
  own quizzes: never a student's private books, bookmarks, questions or
  personal quizzes (CLAUDE.md, "Accounts, roles, and authorization").
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

from .. import track
from ..security import require_owner, require_user
from ..storage import QuizStatus, Reading, User
from .common import prepared_for_in, readable_in

if TYPE_CHECKING:
    from ..app import Deps

#: Sentences reported in one call. A page is well under this; more is not a reader.
MAX_HEARD = 500


class HeardBody(BaseModel):
    segment_ids: list[str] = Field(max_length=MAX_HEARD)


class ChapterProgress(BaseModel):
    title: str | None = Field(
        description="Null for a book without detected chapters, or the pages before the first."
    )
    first_page: int
    sentences: int
    heard: int
    complete: bool
    answered: int
    correct: int
    due: int


class BookProgress(BaseModel):
    document_id: str
    title: str
    chapters: list[ChapterProgress]


class RevisionItem(BaseModel):
    document_id: str
    title: str
    quiz_id: str
    due: int


class ProgressReport(BaseModel):
    books: list[BookProgress]
    chapters_complete: int
    chapter_count: int
    due: int
    revise: list[RevisionItem]


class StudentProgress(BaseModel):
    display_name: str
    books: list[BookProgress]


class ClassProgress(BaseModel):
    class_id: str
    name: str
    students: list[StudentProgress]
    not_sharing: int = Field(description="Active members who have not chosen to share.")


NO_CLASS = "No such class."

CurrentUser = Depends(require_user)

#: A cell a spreadsheet would run as a formula.
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str:
    text = str(value)
    return "'" + text if text.startswith(_FORMULA) else text


def register(app: FastAPI, deps: Deps) -> None:
    """Add the tracking routes to ``app``, acting through ``deps``."""
    store = deps.store

    def book_progress(
        reading: Reading, reader: str, *, class_only: bool = False
    ) -> tuple[BookProgress, list[RevisionItem]] | None:
        prepared = prepared_for_in(deps, reading, required=False)
        if prepared is None:
            return None
        document = reading.document
        title = (document.title or "").strip() or document.filename
        heard = store.get_heard(document.document_id, reader)
        bits = heard.bits if heard is not None and heard.version == document.version else b""
        on = track.today()
        answered: list[track.Answered] = []
        revise: list[RevisionItem] = []
        for quiz in store.quizzes_for(document.document_id, reader):
            if class_only and not (
                quiz.for_class and quiz.status == QuizStatus.PUBLISHED and quiz.creator != reader
            ):
                continue
            pages = {q["question_id"]: q["page_index"] for q in json.loads(quiz.questions)}
            due = 0
            for answer in store.quiz_answers(quiz.quiz_id, reader):
                if answer.question_id not in pages:
                    continue
                is_due = track.is_due(answer.due_on, on)
                due += is_due
                answered.append(track.Answered(pages[answer.question_id], answer.correct, is_due))
            if due:
                revise.append(
                    RevisionItem(
                        document_id=document.document_id, title=title, quiz_id=quiz.quiz_id, due=due
                    )
                )
        rows = track.chapter_rows(
            [(s.index, s.page_index) for s in prepared.segments],
            None
            if prepared.chapters is None
            else [(c.title, c.page_index) for c in prepared.chapters],
            bits,
            answered,
        )
        chapters = [
            ChapterProgress(
                title=r.title,
                first_page=r.first_page,
                sentences=r.sentences,
                heard=r.heard,
                complete=r.complete,
                answered=r.answered,
                correct=r.correct,
                due=r.due,
            )
            for r in rows
        ]
        return BookProgress(
            document_id=document.document_id, title=title, chapters=chapters
        ), revise

    @app.post(
        "/documents/{document_id}/heard",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["track"],
    )
    def mark_heard(
        document_id: str, body: HeardBody, reader: str = Depends(require_owner)
    ) -> Response:
        """Sentences this reader listened to the end of, in the version they read."""
        reading = readable_in(deps, document_id, reader)
        prepared = prepared_for_in(deps, reading)
        assert prepared is not None and reading.document.version is not None
        indices = [
            segment.index
            for segment_id in body.segment_ids
            if (segment := prepared.segment(segment_id)) is not None
        ]
        if indices:
            store.mark_heard(document_id, reader, reading.document.version, indices)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/progress", tags=["track"])
    def my_progress(reader: str = Depends(require_owner)) -> ProgressReport:
        """Every book this reader may read, chapter by chapter, and what is due."""
        ids = [d.document_id for d in store.list_documents(reader)]
        ids += [d.document_id for _, d in store.class_books(reader) if d.document_id not in ids]
        books: list[BookProgress] = []
        revise: list[RevisionItem] = []
        for document_id in dict.fromkeys(ids):
            reading = store.readable_document(document_id, reader)
            found = None if reading is None else book_progress(reading, reader)
            if found is None:
                continue
            books.append(found[0])
            revise.extend(found[1])
        chapters = [c for b in books for c in b.chapters]
        return ProgressReport(
            books=books,
            chapters_complete=sum(c.complete for c in chapters),
            chapter_count=len(chapters),
            due=sum(item.due for item in revise),
            revise=sorted(revise, key=lambda item: -item.due),
        )

    def class_progress(class_id: str, teacher: User) -> ClassProgress:
        classroom = store.class_taught(class_id, teacher.user_id)
        if classroom is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)
        books = [
            d.document_id
            for d in store.list_documents(teacher.user_id)
            if (found := store.publication(d.document_id, teacher.user_id)) is not None
            and class_id in found[1]
        ]
        sharing = store.sharing_members(class_id, teacher.user_id)
        active = [m for m in store.members(class_id, teacher.user_id) if m.state == "active"]
        students = []
        for member in sharing:
            user = store.get_user(member.user_id)
            progress = []
            for document_id in books:
                reading = store.readable_document(document_id, member.user_id)
                if reading is None or reading.as_owner:
                    continue
                found = book_progress(reading, member.user_id, class_only=True)
                if found is not None:
                    progress.append(found[0])
            students.append(
                StudentProgress(display_name=user.display_name if user else "", books=progress)
            )
        return ClassProgress(
            class_id=class_id,
            name=classroom.name,
            students=students,
            not_sharing=len(active) - len(sharing),
        )

    @app.get("/classes/{class_id}/progress", tags=["track"])
    def get_class_progress(class_id: str, user: User = CurrentUser) -> ClassProgress:
        """For the class's teacher: each sharing student's table, and how many do not share."""
        return class_progress(class_id, user)

    @app.get("/classes/{class_id}/progress.csv", tags=["track"])
    def class_progress_csv(class_id: str, user: User = CurrentUser) -> Response:
        """The same, as a spreadsheet: one row per student, book and chapter."""
        report = class_progress(class_id, user)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["student", "book", "chapter", "sentences", "heard", "answered", "correct", "due"]
        )
        for student in report.students:
            for book in student.books:
                for chapter in book.chapters:
                    writer.writerow(
                        _cell(v)
                        for v in (
                            student.display_name,
                            book.title,
                            chapter.title or "",
                            chapter.sentences,
                            chapter.heard,
                            chapter.answered,
                            chapter.correct,
                            chapter.due,
                        )
                    )
        return Response(
            # A byte-order mark, so a spreadsheet opens Sinhala as UTF-8.
            content="﻿" + out.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="class-progress.csv"'},
        )
