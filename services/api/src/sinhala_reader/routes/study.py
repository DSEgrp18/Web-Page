"""Questions about one book, answered only from that book."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, Request
from sinhala_documents.answering import Exchange, answer_with_fallback
from sinhala_documents.passages import build_passages

from ..ratelimit import enforce
from ..schemas import QuestionBody, StudyAnswer, StudyCitation
from ..security import require_owner
from .common import owned_in, prepared_or_409_in

if TYPE_CHECKING:
    from ..app import Deps


def register(app: FastAPI, deps: Deps) -> None:
    """Add the study routes to ``app``, acting through ``deps``."""
    owned = partial(owned_in, deps)
    prepared_or_409 = partial(prepared_or_409_in, deps)

    # -- study -------------------------------------------------------------

    @app.post("/documents/{document_id}/questions", tags=["study"])
    def ask_question(
        document_id: str, body: QuestionBody, request: Request, owner: str = Depends(require_owner)
    ) -> StudyAnswer:
        """Find evidence in this reader's document and answer only from it.

        Authorization happens before passages are built or retrieved. The
        extractive answerer returns the book's own words with playable segment
        citations, or abstains; it never calls a model with text from a document
        the caller does not own.
        """
        document = owned(document_id, owner)
        # After the ownership check, so another reader's book stays absent
        # rather than rate limited; before any model is called.
        enforce(request, "question", owner)
        prepared = prepared_or_409(document)
        result = answer_with_fallback(
            deps.answerer,
            deps.fallback_answerer,
            body.question,
            build_passages(prepared),
            tuple(Exchange(question=turn.question, answer=turn.answer) for turn in body.history),
        )
        return StudyAnswer(
            document_id=document_id,
            answer=result.answer,
            citations=[
                StudyCitation(
                    passage_id=citation.passage_id,
                    page_index=citation.page_index,
                    page_label=citation.page_label,
                    section=citation.section,
                    segment_ids=list(citation.segment_ids),
                    quote=citation.quote,
                )
                for citation in result.citations
            ],
            abstained=result.abstained,
            generated=result.generated,
        )
