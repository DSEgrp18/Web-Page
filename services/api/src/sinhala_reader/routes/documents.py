"""Upload, list, rename, delete and retry books, and serve their files."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, status
from sinhala_documents import DocumentRejected, check_document_bytes, media_type_for

from ..preparation import forget_prepared
from ..ratelimit import enforce
from ..schemas import DocumentDetail, DocumentSummary, JobStatus, RenameBody
from ..security import require_owner
from ..storage import Document, Job, new_id
from .common import _byte_range, _document_detail, owned_in

if TYPE_CHECKING:
    from ..app import Deps


def register(app: FastAPI, deps: Deps) -> None:
    """Add the document routes to ``app``, acting through ``deps``."""
    owned = partial(owned_in, deps)

    # -- documents ---------------------------------------------------------

    @app.post(
        "/documents",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["documents"],
        summary="Upload a PDF, DOCX or image and start preparing it",
    )
    async def upload(
        file: UploadFile, request: Request, owner: str = Depends(require_owner)
    ) -> DocumentDetail:
        """Accept a book and return immediately with a job to watch.

        Preparation of a whole book takes tens of seconds, so this never waits
        for it. The response is 202 with a job, not 201 with a finished document.
        """
        # Counted before the body is read: a refused upload should not cost
        # the server 200 MB of network first.
        enforce(request, "upload", owner)
        data = await file.read()
        try:
            filename = file.filename or "document.pdf"
            check_document_bytes(data, filename)
        except DocumentRejected as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

        document = deps.store.put_document(
            Document(
                document_id=new_id("doc"),
                owner=owner,
                filename=filename,
                size_bytes=len(data),
            )
        )
        deps.store.put_source(document.document_id, data)
        job = deps.preparation.start(
            document,
            Job(
                job_id=new_id("job"),
                document_id=document.document_id,
                owner=owner,
                kind="prepare",
            ),
        )
        return _document_detail(deps.store, document.document_id, owner, job)

    @app.get("/documents", tags=["documents"])
    def list_documents(owner: str = Depends(require_owner)) -> list[DocumentSummary]:
        """This reader's books, with where they stopped in each.

        The positions come from one query rather than one per book: the library
        draws a progress bar on every card, and a request per card is a request
        per book on a student's phone data.
        """
        positions = deps.store.list_progress(owner)
        jobs = deps.store.latest_jobs(owner)
        return [
            DocumentSummary.of(
                d,
                progress=positions.get(d.document_id),
                media_type=media_type_for(d.filename, deps.store.get_source(d.document_id)),
                job=jobs.get(d.document_id),
            )
            for d in deps.store.list_documents(owner)
        ]

    @app.get("/documents/{document_id}", tags=["documents"])
    def get_document(document_id: str, owner: str = Depends(require_owner)) -> DocumentDetail:
        owned(document_id, owner)
        return _document_detail(deps.store, document_id, owner)

    @app.patch("/documents/{document_id}", tags=["documents"])
    def rename_document(
        document_id: str, body: RenameBody, owner: str = Depends(require_owner)
    ) -> DocumentDetail:
        """Give a book the reader's own name.

        The upload filename is kept as it was. A rename is a label the reader
        chose, not a correction of what they uploaded, and losing the original
        would make a re-upload look like a different book.

        An empty or whitespace-only title clears the name rather than storing
        blanks, so the filename comes back rather than a card with no heading.
        """
        document = owned(document_id, owner)
        title = body.title.strip()
        deps.store.put_document(replace(document, title=title or None))
        return _document_detail(deps.store, document_id, owner)

    @app.get("/documents/{document_id}/file", tags=["documents"])
    def get_document_file(
        document_id: str, request: Request, owner: str = Depends(require_owner)
    ) -> Response:
        """The PDF exactly as it was uploaded, in whole or in part.

        The reading workspace shows the original page beside the extracted
        text, so the bytes have to reach the browser. Ownership is enforced
        here like everywhere else: another reader's document is *absent*, not
        forbidden, because a 403 on a real id confirms the id is real.

        **Range requests are the point, not a nicety.** pdf.js asks for the
        cross-reference table at the end of the file, then only the objects for
        the page being shown. Without ranges, opening page 1 of a 50 MB scan
        downloads 50 MB, and so does drawing its thumbnail in the library. With
        them it downloads a few tens of kilobytes. The reader this is for is on
        a phone, on their own data.

        ``inline`` rather than ``attachment``: this is rendered in a canvas by
        the page, not downloaded. And ``private, no-store`` because a shared
        machine's disk cache is not a place for somebody's private textbook.
        """
        document = owned(document_id, owner)
        data = deps.store.get_source(document_id)
        if data is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")

        headers = {
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
            # Advertised whether or not this request used one: pdf.js checks
            # for this before it will attempt partial loading at all.
            "Accept-Ranges": "bytes",
        }
        span = _byte_range(request.headers.get("range"), len(data))
        if span is None:
            return Response(
                content=data,
                media_type=media_type_for(document.filename, data) or "application/octet-stream",
                headers=headers,
            )

        start, end = span
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return Response(
            content=data[start : end + 1],
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=media_type_for(document.filename, data) or "application/octet-stream",
            headers=headers,
        )

    @app.delete(
        "/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["documents"],
    )
    def delete_document(document_id: str, owner: str = Depends(require_owner)) -> Response:
        """Delete the upload and everything derived from it.

        CLAUDE.md requires deletion to remove derived text, audio and caches.
        Anything left behind is private content that outlived the decision to
        delete it.
        """
        if not deps.store.delete_document(document_id, owner):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
        forget_prepared(document_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/documents/{document_id}/retry",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["documents"],
        summary="Prepare a book again after its preparation failed",
    )
    def retry_preparation(
        document_id: str, request: Request, owner: str = Depends(require_owner)
    ) -> DocumentDetail:
        """Start a new job on the book as uploaded, when the last one failed.

        The file is already stored, so a reader whose book stopped when the
        server restarted does not have to find it and upload it again. A new
        job, not a reset of the old one: the failure stays on record, and a
        worker still holding the old job cannot mistake it for its own.

        Refused with 409 while the book is being prepared or once it is ready,
        and when the file itself was rejected, since that would fail the same
        way again. Another reader's book is absent, as everywhere.
        """
        document = owned(document_id, owner)
        jobs = deps.store.jobs_for(document_id, owner)
        # The same work as an upload, so the same allowance.
        enforce(request, "upload", owner)
        if not jobs or not jobs[-1].can_retry:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Only a book whose preparation failed, and could succeed, can be tried again.",
            )
        if deps.store.get_source(document_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
        job = deps.preparation.start(
            document,
            Job(
                job_id=new_id("job"),
                document_id=document_id,
                owner=owner,
                kind="prepare",
            ),
        )
        return _document_detail(deps.store, document_id, owner, job)

    @app.get("/documents/{document_id}/jobs/{job_id}", tags=["documents"])
    def get_job(document_id: str, job_id: str, owner: str = Depends(require_owner)) -> JobStatus:
        owned(document_id, owner)
        job = deps.store.get_job(job_id, owner)
        if job is None or job.document_id != document_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
        return JobStatus.of(job)
