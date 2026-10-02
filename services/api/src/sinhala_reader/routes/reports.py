"""Report a problem: with a sentence, a practice question, or the site itself.

Anyone signed in may report on a book they may read; the book's owner reads
the reports on it, without who sent them. A report without a book is about the
site (the accessibility statement links here), and only an operator reads it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..ratelimit import enforce
from ..security import require_owner
from ..storage import ProblemReport, ReportKind, new_id
from .common import owned_in, prepared_for_in, readable_in

if TYPE_CHECKING:
    from ..app import Deps


class ReportBody(BaseModel):
    kind: ReportKind
    message: str = Field(min_length=1, max_length=1000)
    document_id: str | None = None
    segment_id: str | None = None
    quiz_id: str | None = None
    question_id: str | None = None


class ReportView(BaseModel):
    report_id: str
    kind: str
    message: str
    segment_id: str | None
    sentence: str | None = Field(description="The reported sentence, if it is still in the book.")
    quiz_id: str | None
    question_id: str | None
    created_at: str
    handled_at: str | None = None


def register(app: FastAPI, deps: Deps) -> None:
    """Add the report routes to ``app``, acting through ``deps``."""
    store = deps.store

    @app.post("/reports", status_code=status.HTTP_201_CREATED, tags=["reports"])
    def report(body: ReportBody, request: Request, reader: str = Depends(require_owner)) -> None:
        """Record a problem. What it points at must be something the reader can see."""
        if body.document_id is None and (body.segment_id or body.quiz_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say which book.")
        if body.document_id is not None:
            reading = readable_in(deps, body.document_id, reader)
            prepared = prepared_for_in(deps, reading, required=False)
            if body.segment_id and (prepared is None or prepared.segment(body.segment_id) is None):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
            if body.quiz_id:
                quiz = store.quiz_for(body.quiz_id, reader)
                if quiz is None or quiz.document_id != body.document_id:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "No such quiz.")
        enforce(request, "report", reader)
        store.put_report(
            ProblemReport(
                report_id=new_id("rpt"),
                reporter=reader,
                kind=body.kind,
                message=body.message.strip(),
                document_id=body.document_id,
                segment_id=body.segment_id,
                quiz_id=body.quiz_id,
                question_id=body.question_id,
            )
        )

    @app.get("/documents/{document_id}/reports", tags=["reports"])
    def reports(document_id: str, owner: str = Depends(require_owner)) -> list[ReportView]:
        """The reports on the owner's book, newest first. Who sent them is not said."""
        document = owned_in(deps, document_id, owner)
        reading = readable_in(deps, document.document_id, owner)
        prepared = prepared_for_in(deps, reading, required=False)
        views = []
        for found in store.reports_on(document_id, owner):
            segment = prepared.segment(found.segment_id) if prepared and found.segment_id else None
            views.append(
                ReportView(
                    report_id=found.report_id,
                    kind=str(found.kind),
                    message=found.message,
                    segment_id=found.segment_id,
                    sentence=segment.display_text if segment else None,
                    quiz_id=found.quiz_id,
                    question_id=found.question_id,
                    created_at=found.created_at,
                    handled_at=found.handled_at,
                )
            )
        return views

    @app.post(
        "/documents/{document_id}/reports/{report_id}/handled",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["reports"],
    )
    def mark_handled(
        document_id: str, report_id: str, owner: str = Depends(require_owner)
    ) -> None:
        """The book's owner marks a report as handled."""
        owned_in(deps, document_id, owner)
        if store.mark_report_handled(document_id, owner, report_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report.")
