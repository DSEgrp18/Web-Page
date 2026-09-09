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

What is deliberately absent: accounts, a database, a job queue, and object
storage. See ``security.py``, ``storage.py`` and ``preparation.py`` — each says
what stands in for the real thing and what that costs.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile, status
from sinhala_documents import DocumentRejected, check_pdf_bytes
from sinhala_tts.adapter import DevelopmentAdapter, TextNotSpeakableError, TtsAdapter
from sinhala_tts.adapter import health as adapter_health

from .audio import SynthesisService
from .preparation import PreparationService, forget_prepared, get_prepared
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
from .security import auth_mode, is_development_auth, require_owner
from .storage import Document, InMemoryStore, Job, Progress, Store, new_id

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
    ) -> None:
        self.store = store or InMemoryStore()
        self.adapter = adapter or DevelopmentAdapter()
        self.preparation = PreparationService(self.store, run_in_background=run_in_background)
        self.synthesis = SynthesisService(self.adapter, self.store)


def create_app(deps: Deps | None = None) -> FastAPI:
    """Build the app around an explicit set of dependencies."""
    deps = deps or Deps()
    app = FastAPI(
        title="Sinhala Accessible Reader",
        version="0.0.1",
        summary="Upload a Sinhala PDF, read it, and listen to it.",
    )
    app.state.deps = deps

    def owned(document_id: str, owner: str) -> Document:
        document = deps.store.get_document(document_id, owner)
        if document is None:
            # Deliberately the same answer as "no such document".
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
        return document

    def prepared_or_409(document: Document):
        prepared = get_prepared(document.document_id)
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
                "Audio is a placeholder tone, not speech. It must not be used as narration."
            )
        if isinstance(deps.store, InMemoryStore):
            limitations.append(
                "Storage is in memory. Documents, audio and reading positions are lost "
                "when this process stops."
            )
        if is_development_auth():
            limitations.append(
                "Authentication is a trusted header. Anyone can claim to be anyone; "
                "do not expose this server."
            )
        return {
            "alive": report.alive,
            "serving": report.serving,
            "readiness": report.readiness,
            "real_model": deps.adapter.is_real_model,
            "model_version": deps.adapter.model_version if deps.adapter.is_real_model else None,
            "auth_mode": auth_mode() or "unconfigured",
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
