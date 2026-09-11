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

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sinhala_documents import DocumentRejected, check_pdf_bytes
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
    DocumentDetail,
    DocumentSummary,
    JobStatus,
    PageDetail,
    ProgressBody,
    ProgressDetail,
    SegmentDetail,
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
    Document,
    Job,
    Progress,
    Store,
    build_store,
    is_durable,
    new_id,
)

#: Names the audio a placeholder in the one place a client cannot miss it.
REAL_MODEL_HEADER = "X-Reader-Real-Model"


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
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[OWNER_HEADER, "Authorization", "Content-Type"],
            expose_headers=[REAL_MODEL_HEADER],
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
        return {
            "alive": report.alive,
            "serving": report.serving,
            "readiness": report.readiness,
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
        return [DocumentSummary.of(d) for d in deps.store.list_documents(owner)]

    @app.get("/documents/{document_id}", tags=["documents"])
    def get_document(document_id: str, owner: str = Depends(require_owner)) -> DocumentDetail:
        owned(document_id, owner)
        return _document_detail(deps.store, document_id, owner)

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
        if prepared.segment(body.segment_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such segment.")
        assert document.version is not None
        progress = deps.store.put_progress(
            Progress(
                document_id=document_id,
                owner=owner,
                document_version=document.version,
                segment_id=body.segment_id,
                offset_seconds=body.offset_seconds,
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


def _document_detail(
    store: Store, document_id: str, owner: str, job: Job | None = None
) -> DocumentDetail:
    document = store.get_document(document_id, owner)
    assert document is not None
    jobs = store.jobs_for(document_id, owner)
    latest = job or (jobs[-1] if jobs else None)
    return DocumentDetail.of(document, latest)


#: The app a server runs. Tests build their own with explicit dependencies.
app = create_app()
