"""The reader API: upload a book, get its segments, hear them, resume where you were.

This is the spine CLAUDE.md's step 3 asks for — digital PDF to selected page to
audio to pause and resume — with the parts that do not exist yet named rather
than faked.

Three rules run through every route:

* **Ownership is the store's job, not the route's.** Every read takes an owner
  and returns nothing for anyone else's document, so a forgotten check is a
  missing argument rather than a silent leak.
* **A missing document and someone else's document look identical.** Both are
  404. A 403 on an id that exists confirms it exists, and these are private
  books belonging to identifiable students.
* **Placeholder audio announces itself.** Every audio response carries whether a
  real model produced it, in a header and in the manifest, because a listener
  cannot tell a tone from speech they were not expecting.

What is deliberately absent: object storage. Accounts, a database and a job
queue are not — ``SINHALA_READER_AUTH=sessions`` gives real sign-in,
``SINHALA_READER_DATABASE_URL`` selects PostgreSQL, and
``SINHALA_READER_QUEUE=celery`` moves preparation onto a broker. Without each,
the placeholder is used and ``/readiness`` says so on every call.

See ``security.py``, ``storage.py`` and ``preparation.py`` — each says what
stands in for the real thing and what that costs.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sinhala_documents import DocumentRejected, check_pdf_bytes
from sinhala_documents.answerer import answer_question
from sinhala_documents.passages import build_passages
from sinhala_tts.adapter import ReadinessState, TextNotSpeakableError, TtsAdapter
from sinhala_tts.adapter import health as adapter_health

from . import passwords
from .accounts import router as accounts_router
from .adapters import ADAPTER_ENV, adapter_mode, build_adapter, loaded_model_version, warm
from .audio import SynthesisService
from .preparation import (
    PreparationService,
    forget_prepared,
    get_prepared,
    in_thread,
    inline,
)
from .queue import QUEUE_ENV, REDIS_URL_ENV, build_app, queue_mode, send_prepare, uses_celery
from .schemas import (
    AudioManifest,
    BookmarkBody,
    BookmarkDetail,
    DocumentDetail,
    DocumentSummary,
    JobStatus,
    PageDetail,
    ProgressBody,
    ProgressDetail,
    QuestionBody,
    RenameBody,
    SegmentDetail,
    StudyAnswer,
    StudyCitation,
)
from .security import (
    AUTH_MODE_ENV,
    ORIGINS_ENV,
    OWNER_HEADER,
    allowed_origins,
    auth_mode,
    is_development_auth,
    require_owner,
    uses_sessions,
)
from .storage import (
    DATABASE_URL_ENV,
    Bookmark,
    Document,
    Job,
    Progress,
    Store,
    build_store,
    is_durable,
    new_id,
)
from .structure import structure_limitations, structure_mode

#: Names the audio a placeholder in the one place a client cannot miss it.
REAL_MODEL_HEADER = "X-Reader-Real-Model"

#: How many bookmarks one reader may keep in one document. CLAUDE.md asks for
#: quotas; this is the one that stops a bookmark list from becoming a place to
#: store text. Well beyond a reader marking every section of a textbook, and far
#: short of a list nobody could navigate by ear.
MAX_BOOKMARKS = 500


class Deps:
    """The composition root.

    Implementations are chosen once, here, rather than imported where they are
    used — so a test swaps a store or an adapter without patching a module, and
    a deployment swaps them without touching a route.
    """

    def __init__(
        self,
        store: Store | None = None,
        adapter: TtsAdapter | None = None,
        *,
        run_in_background: bool = True,
        warm_on_start: bool = True,
    ) -> None:
        self.store = store or build_store()
        # Chosen from configuration, defaulting to the labelled placeholder.
        self.adapter = adapter or build_adapter()
        #: Load the checkpoint at start-up rather than in the first request.
        #: Tests turn it off to hold an adapter in a chosen state.
        self.warm_on_start = warm_on_start
        #: Where preparation runs. ``run_in_background=False`` wins over
        #: configuration: a test asking for inline work must get inline work,
        #: not whatever a stray environment variable selects.
        self.celery = build_app() if run_in_background and uses_celery() else None
        self.preparation = PreparationService(
            self.store, dispatch=self._dispatcher(run_in_background)
        )
        self.synthesis = SynthesisService(self.adapter, self.store)

    def _dispatcher(self, run_in_background: bool):
        if not run_in_background:
            return inline
        if self.celery is not None:
            celery = self.celery

            def to_the_queue(service, document_id: str, job_id: str) -> None:
                send_prepare(celery, document_id, job_id)

            return to_the_queue
        return in_thread


def create_app(deps: Deps | None = None) -> FastAPI:
    """Build the app around an explicit set of dependencies."""
    deps = deps or Deps()
    app = FastAPI(
        title="Sinhala Accessible Reader",
        version="0.0.1",
        summary="Upload a Sinhala PDF, read it, and listen to it.",
    )
    app.state.deps = deps

    # Load the checkpoint while the process starts rather than inside the first
    # request. It takes over a minute on this hardware; a reader who presses
    # play and waits that long has been failed whatever happens next.
    app.state.warm_up = warm(deps.adapter) if deps.warm_on_start else None

    # Register, sign in, sign out, change a password. Mounted whatever the auth
    # mode is: in development the routes answer 503 and say which setting turns
    # them on, which is more use than a 404 that looks like a missing feature.
    app.include_router(accounts_router)

    # The reader UI is served from its own origin, so without this the browser
    # blocks every request before it leaves the machine and the interface can
    # only say it is offline. Unset means no browser may call this API: the
    # origins have to be named, and `X-Reader-Real-Model` has to be exposed
    # explicitly or the reader cannot tell a placeholder tone from speech.
    origins = allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            # `Range` has to be allowed or the preflight for a partial PDF read
            # fails, and pdf.js falls back to fetching whole books.
            allow_headers=[OWNER_HEADER, "Authorization", "Content-Type", "Range"],
            # Cross-origin, a header the browser will not expose does not exist
            # as far as the page is concerned: without `Content-Range` pdf.js
            # cannot tell which bytes it got, and without `X-Reader-Real-Model`
            # the reader cannot tell a placeholder tone from speech.
            expose_headers=[REAL_MODEL_HEADER, "Content-Range", "Accept-Ranges", "Content-Length"],
            # Identity travels in a header, not a cookie. Allowing credentials
            # would let a third-party page ride along on an ambient session the
            # moment real authentication replaces the header.
            allow_credentials=False,
            max_age=600,
        )

    def owned(document_id: str, owner: str) -> Document:
        document = deps.store.get_document(document_id, owner)
        if document is None:
            # Deliberately the same answer as "no such document".
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
        return document

    def prepared_or_409(document: Document):
        prepared = get_prepared(deps.store, document.document_id)
        if prepared is None or document.version is None:
            jobs = deps.store.jobs_for(document.document_id, document.owner)
            latest = jobs[-1] if jobs else None
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This document is not ready yet ({latest.state if latest else 'unknown'}).",
            )
        return prepared

    # -- health ------------------------------------------------------------

    @app.get("/health", tags=["operations"])
    def health() -> dict:
        """Liveness. Says nothing about whether a model is loaded."""
        return {"alive": True}

    @app.get("/readiness", tags=["operations"])
    def readiness() -> dict:
        """Readiness, and every way this deployment is not production.

        CLAUDE.md requires liveness and model readiness to be separate, and
        requires unenforced or missing pieces to be reported honestly rather
        than implied by silence.
        """
        report = adapter_health(deps.adapter)
        limitations = list(report.notes)
        if not deps.adapter.is_real_model:
            limitations.append(
                "Audio is a placeholder tone, not speech. It must not be used as narration. "
                f"Set {ADAPTER_ENV}=xtts to serve the real voice."
            )
        elif report.readiness in (ReadinessState.NOT_LOADED, ReadinessState.LOADING):
            # A cold start, not a fault. Said plainly so an operator waits
            # rather than restarting the process and starting the load again.
            limitations.append(
                "The voice is still loading and cannot narrate yet. This takes over a "
                "minute from cold; it is not a failure."
            )
        elif report.readiness is ReadinessState.FAILED:
            # This one *is* a fault, and it has to be said. Without it a server
            # whose voice is dead reports a state string and four unrelated
            # notes, and reads as healthy to anyone skimming.
            limitations.append(
                "The voice failed to load, so nothing can be narrated. "
                + (report.detail or "No reason was recorded.")
            )
        if not uses_celery():
            limitations.append(
                "Preparation runs in a thread. Work in flight is lost if this process "
                f"stops, and its job stays 'running' for ever. Set {QUEUE_ENV}=celery "
                f"and {REDIS_URL_ENV} for a durable queue."
            )
        if not is_durable(deps.store):
            limitations.append(
                "Storage is in memory. Documents, audio and reading positions are lost "
                f"when this process stops. Set {DATABASE_URL_ENV} to use PostgreSQL."
            )
        if is_development_auth():
            limitations.append(
                "Authentication is a trusted header. Anyone can claim to be anyone; "
                f"do not expose this server. Set {AUTH_MODE_ENV}=sessions for accounts."
            )
        elif uses_sessions():
            # Accounts exist, and these are the ways they are still not
            # finished. Saying nothing here would let "we have logins" stand in
            # for "this is safe to expose".
            limitations.append(
                "There is no rate limiting. Password guessing and email enumeration "
                "through registration are both unthrottled."
            )
            limitations.append(
                "There is no email verification and no password reset. A reader who "
                "forgets their password cannot recover the account."
            )
            if passwords.is_weakened():
                limitations.append(
                    "Passwords are being hashed more cheaply than this build intends. "
                    "This should only ever happen in tests."
                )
        if not is_development_auth() and not uses_sessions():
            limitations.append(
                f"No authentication is configured, so every request is refused. "
                f"Set {AUTH_MODE_ENV} to one of: sessions, development."
            )
        if not origins:
            limitations.append(
                "No browser origin is allowed, so the reader interface cannot reach this "
                f"server. Set {ORIGINS_ENV} to the address it is served from."
            )
        elif "*" in origins:
            limitations.append(
                "Any website may call this API from a browser. With header identity that "
                "means any page can read any reader's documents."
            )
        limitations.extend(structure_limitations())
        return {
            "alive": report.alive,
            "serving": report.serving,
            "readiness": report.readiness,
            "structure": structure_mode(),
            "real_model": deps.adapter.is_real_model,
            # Not `adapter.model_version`: that loads the bundle if it has not
            # been loaded, and a readiness probe that blocks for a minute and a
            # half gets killed and reported as an outage rather than a cold start.
            "model_version": loaded_model_version(deps.adapter),
            "voice": adapter_mode(),
            "device": report.device,
            "voice_detail": report.detail,
            "auth_mode": auth_mode() or "unconfigured",
            "queue": queue_mode(),
            "limitations": limitations,
        }

    # -- documents ---------------------------------------------------------

    @app.post(
        "/documents",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["documents"],
        summary="Upload a PDF and start preparing it",
    )
    async def upload(file: UploadFile, owner: str = Depends(require_owner)) -> DocumentDetail:
        """Accept a book and return immediately with a job to watch.

        Preparation of a whole book takes tens of seconds, so this never waits
        for it. The response is 202 with a job, not 201 with a finished document.
        """
        data = await file.read()
        try:
            check_pdf_bytes(data)
        except DocumentRejected as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

        document = deps.store.put_document(
            Document(
                document_id=new_id("doc"),
                owner=owner,
                filename=file.filename or "document.pdf",
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
        return [
            DocumentSummary.of(d, progress=positions.get(d.document_id))
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
        owned(document_id, owner)
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
            return Response(content=data, media_type="application/pdf", headers=headers)

        start, end = span
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return Response(
            content=data[start : end + 1],
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/pdf",
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

    @app.get("/documents/{document_id}/jobs/{job_id}", tags=["documents"])
    def get_job(document_id: str, job_id: str, owner: str = Depends(require_owner)) -> JobStatus:
        owned(document_id, owner)
        job = deps.store.get_job(job_id, owner)
        if job is None or job.document_id != document_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
        return JobStatus.of(job)

    # -- structure ---------------------------------------------------------

    @app.get("/documents/{document_id}/pages/{page_index}", tags=["reading"])
    def get_page(
        document_id: str, page_index: int, owner: str = Depends(require_owner)
    ) -> PageDetail:
        """One page's segments, in reading order, with what cannot be read."""
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        page = prepared.page(page_index)
        if page is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such page.")
        return PageDetail.of(page)

    @app.get("/documents/{document_id}/segments/{segment_id}", tags=["reading"])
    def get_segment(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> SegmentDetail:
        document = owned(document_id, owner)
        segment = prepared_or_409(document).segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        return SegmentDetail.of(segment)

    # -- audio -------------------------------------------------------------

    @app.get("/documents/{document_id}/segments/{segment_id}/audio", tags=["reading"])
    def get_audio(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> Response:
        """The audio for one segment, generated on demand and then cached.

        Generating on demand is what lets a reader start listening to the page
        they asked for while the rest of the book is still being prepared.
        Concurrent requests for the same segment are deduplicated, so prefetch
        and playback cannot generate it twice.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")

        assert document.version is not None
        try:
            record = deps.synthesis.synthesize(
                text=segment.display_text,
                document_id=document_id,
                owner=owner,
                segment_id=segment_id,
                document_version=document.version,
            )
        except TextNotSpeakableError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "This segment has nothing to say."
            ) from error

        return Response(
            content=record.wav,
            media_type="audio/wav",
            headers={
                REAL_MODEL_HEADER: "true" if record.is_real_model else "false",
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": f'inline; filename="{segment_id}.wav"',
            },
        )

    @app.get("/documents/{document_id}/segments/{segment_id}/audio/manifest", tags=["reading"])
    def get_audio_manifest(
        document_id: str, segment_id: str, owner: str = Depends(require_owner)
    ) -> AudioManifest:
        """What produced this segment's audio, without downloading it."""
        document = owned(document_id, owner)
        segment = prepared_or_409(document).segment(segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        assert document.version is not None
        key = deps.synthesis.cache_key_for(segment.display_text, document.version)
        record = deps.store.get_audio(key, owner)
        return AudioManifest(
            segment_id=segment_id,
            cache_key=key,
            generated=record is not None,
            real_model=record.is_real_model if record else deps.adapter.is_real_model,
            voice_id=record.voice_id if record else None,
            model_version=record.model_version if record else None,
            duration_seconds=record.duration_seconds if record else None,
        )

    # -- study -------------------------------------------------------------

    @app.post("/documents/{document_id}/questions", tags=["study"])
    def ask_question(
        document_id: str, body: QuestionBody, owner: str = Depends(require_owner)
    ) -> StudyAnswer:
        """Find evidence in this reader's document and answer only from it.

        Authorization happens before passages are built or retrieved. The
        extractive answerer returns the book's own words with playable segment
        citations, or abstains; it never calls a model with text from a document
        the caller does not own.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        result = answer_question(body.question, build_passages(prepared))
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
        )

    # -- bookmarks ---------------------------------------------------------

    @app.post("/documents/{document_id}/bookmarks", tags=["reading"])
    def add_bookmark(
        document_id: str,
        body: BookmarkBody,
        response: Response,
        owner: str = Depends(require_owner),
    ) -> BookmarkDetail:
        """Mark a place worth coming back to.

        Bookmarking the same sentence twice is not an error and does not make a
        second entry — it updates the note. The control is a button pressed
        without seeing what it did, and a reader navigating a list by ear should
        not have to find and delete a duplicate they did not know they made.

        Answers 201 when the bookmark is new and 200 when it replaced one, so an
        interface can say which happened rather than guess.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(body.segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")

        existing = deps.store.list_bookmarks(document_id, owner)
        if len(existing) >= MAX_BOOKMARKS and not any(
            b.segment_id == body.segment_id for b in existing
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This document already has {MAX_BOOKMARKS} bookmarks. "
                "Remove one before adding another.",
            )

        assert document.version is not None
        note = (body.note or "").strip() or None
        bookmark, created = deps.store.put_bookmark(
            Bookmark(
                bookmark_id=new_id("bmk"),
                document_id=document_id,
                owner=owner,
                document_version=document.version,
                segment_id=body.segment_id,
                note=note,
            )
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return BookmarkDetail.of(bookmark, segment=segment, current_version=document.version)

    @app.get("/documents/{document_id}/bookmarks", tags=["reading"])
    def list_bookmarks(
        document_id: str, owner: str = Depends(require_owner)
    ) -> list[BookmarkDetail]:
        """This reader's bookmarks, in the order they appear in the book.

        Reading order rather than the order they were made: this is a way to
        move through a document, and a list that jumps back and forth is one a
        reader has to hold in their head rather than step down.

        The sentences come from the document as it stands. A bookmark whose
        segment is no longer there is still listed — losing it silently would
        leave a reader wondering what they had marked — but it is marked as not
        found rather than described with text that is not its own.
        """
        document = owned(document_id, owner)
        # Deliberately not prepared_or_409: a reader whose book is being
        # re-extracted should still be able to see what they marked, even if the
        # sentences cannot be filled in yet.
        prepared = get_prepared(deps.store, document_id)
        bookmarks = deps.store.list_bookmarks(document_id, owner)
        details = [
            BookmarkDetail.of(
                bookmark,
                segment=prepared.segment(bookmark.segment_id) if prepared else None,
                current_version=document.version,
            )
            for bookmark in bookmarks
        ]
        positions = (
            {s.segment_id: s.index for s in prepared.segments} if prepared is not None else {}
        )
        # Anything that cannot be placed in the book goes last, oldest first,
        # rather than being dropped into the middle at an arbitrary point.
        return sorted(
            details,
            key=lambda d: (
                (0, positions[d.segment_id], "")
                if d.segment_id in positions
                else (1, 0, d.created_at)
            ),
        )

    @app.delete(
        "/documents/{document_id}/bookmarks/{bookmark_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["reading"],
    )
    def delete_bookmark(
        document_id: str, bookmark_id: str, owner: str = Depends(require_owner)
    ) -> Response:
        owned(document_id, owner)
        bookmark = deps.store.get_bookmark(bookmark_id, owner)
        if bookmark is None or bookmark.document_id != document_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bookmark.")
        deps.store.delete_bookmark(bookmark_id, owner)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # -- reading position --------------------------------------------------

    @app.put("/documents/{document_id}/progress", tags=["reading"])
    def save_progress(
        document_id: str, body: ProgressBody, owner: str = Depends(require_owner)
    ) -> ProgressDetail:
        """Remember where the reader is, against the version they were reading.

        Storing the version matters: text corrected since is a different
        document, and dropping the reader at the same segment id in changed
        text would put them somewhere they never were.
        """
        document = owned(document_id, owner)
        prepared = prepared_or_409(document)
        segment = prepared.segment(body.segment_id)
        if segment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        assert document.version is not None
        progress = deps.store.put_progress(
            Progress(
                document_id=document_id,
                owner=owner,
                document_version=document.version,
                segment_id=body.segment_id,
                offset_seconds=body.offset_seconds,
                # Resolved here, while the prepared document is already loaded
                # to check the segment exists. The library reads it back to draw
                # a progress bar without loading anything.
                segment_index=segment.index,
            )
        )
        return ProgressDetail.of(progress, current_version=document.version)

    @app.get("/documents/{document_id}/progress", tags=["reading"])
    def read_progress(document_id: str, owner: str = Depends(require_owner)) -> ProgressDetail:
        document = owned(document_id, owner)
        progress = deps.store.get_progress(document_id, owner)
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No saved position.")
        return ProgressDetail.of(progress, current_version=document.version)

    return app


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse one `Range: bytes=…` into inclusive offsets, or None for the lot.

    Deliberately narrow. Only a single range is honoured, because that is all
    pdf.js asks for and a multipart/byteranges response is a lot of machinery
    for a case that does not arise here. Anything unparseable, reversed, or
    past the end returns None, which serves the whole file — a correct answer
    to the request, just not a partial one. RFC 9110 permits ignoring a Range
    that cannot be satisfied, and serving 200 keeps a strange header from
    turning into a failed page rather than a slower one.
    """
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    spec = header[len("bytes=") :].strip()
    first, _, last = spec.partition("-")
    try:
        if not first:
            # `bytes=-500`: the final 500 bytes, which is how pdf.js finds the
            # cross-reference table.
            length = int(last)
            if length <= 0:
                return None
            return max(0, size - length), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start > end or start >= size:
        return None
    return start, min(end, size - 1)


def _document_detail(
    store: Store, document_id: str, owner: str, job: Job | None = None
) -> DocumentDetail:
    document = store.get_document(document_id, owner)
    assert document is not None
    jobs = store.jobs_for(document_id, owner)
    latest = job or (jobs[-1] if jobs else None)
    return DocumentDetail.of(document, latest, progress=store.get_progress(document_id, owner))


#: The app a server runs. Tests build their own with explicit dependencies.
app = create_app()
