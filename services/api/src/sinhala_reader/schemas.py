"""What the API sends back.

Separate from the storage and pipeline types on purpose. Those change as the
pipeline learns things; this is a contract a reader UI is written against, and
the two should not be forced to move together.

Two things are shaped by accessibility rather than by convenience:

* **Notes are part of the payload, not an error path.** A page that could not be
  read, a reading order that may be wrong, an image nobody described — these are
  ordinary states of a real book, and a reader who cannot see the page needs
  them announced. Returning them alongside the text is what lets an interface
  put them in a live region.
* **Whether audio is real is always present.** Never inferred, never optional.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sinhala_documents.pipeline import ReadablePage, ReadableSegment
from sinhala_documents.structure import BlockRole

from .storage import Bookmark, Document, Job, Progress


class Box(BaseModel):
    """A rectangle on the page, measured downwards from the top."""

    x0: float
    top: float
    x1: float
    bottom: float


class SegmentDetail(BaseModel):
    """One thing the reader plays, highlights, or resumes at."""

    segment_id: str
    index: int
    page_index: int
    page_label: str | None = Field(
        default=None,
        description=(
            "The page number as printed, when the book declares one. Not the file position."
        ),
    )
    display_text: str = Field(description="What a reader sees, and what highlighting points at.")
    spoken_text: str = Field(
        description="Normalised Sinhala with numbers written out. Reviewable by a person."
    )
    boxes: list[Box] = Field(
        default_factory=list, description="Lines this segment covers, for highlighting."
    )
    role: BlockRole = Field(
        default=BlockRole.UNKNOWN,
        description=(
            "What kind of thing this segment is part of: a paragraph, a heading, a "
            "figure caption, a row of the contents. Decides how its numbers were read, "
            "and lets a reader be told that what follows is a caption rather than the "
            "next sentence of the paragraph - which somebody listening cannot see."
        ),
    )
    level: int | None = Field(
        default=None,
        description="Heading depth, 1 outermost. Null for anything that is not a heading.",
    )

    @classmethod
    def of(cls, segment: ReadableSegment) -> SegmentDetail:
        # model_text — the romanised ASCII — is deliberately not exposed. It is
        # meaningful only to the synthesiser, and showing it invites someone to
        # display or index it.
        return cls(
            segment_id=segment.segment_id,
            index=segment.index,
            page_index=segment.page_index,
            page_label=segment.page_label,
            role=segment.role,
            level=segment.level,
            display_text=segment.display_text,
            spoken_text=segment.spoken_text,
            boxes=[Box(x0=b.x0, top=b.top, x1=b.x1, bottom=b.bottom) for b in segment.boxes],
        )


class PageDetail(BaseModel):
    page_index: int
    page_label: str | None = None
    kind: str = Field(description="text, image, mixed, or empty.")
    quality: str = Field(description="accepted, needs_review, or undecodable.")
    notes: list[str] = Field(
        default_factory=list,
        description="What a reader loses on this page, in words fit to announce.",
    )
    segments: list[SegmentDetail] = Field(default_factory=list)

    @classmethod
    def of(cls, page: ReadablePage) -> PageDetail:
        return cls(
            page_index=page.page_index,
            page_label=page.page_label,
            kind=page.kind.value,
            quality=page.quality.value,
            notes=list(page.notes),
            segments=[SegmentDetail.of(s) for s in page.segments],
        )


class JobStatus(BaseModel):
    job_id: str
    kind: str
    state: str = Field(description="queued, running, succeeded, failed, or cancelled.")
    stage: str
    detail: str | None = Field(
        default=None, description="Why it failed. Never contains document text."
    )
    updated_at: str

    @classmethod
    def of(cls, job: Job) -> JobStatus:
        return cls(
            job_id=job.job_id,
            kind=job.kind,
            state=job.state.value,
            stage=job.stage,
            detail=job.detail,
            updated_at=job.updated_at,
        )


class ReadingPosition(BaseModel):
    """Where a reader stopped, as the library needs it.

    Enough to draw a progress bar and order books by "recently opened" without
    a request per card.
    """

    segment_id: str
    segment_index: int
    updated_at: str
    stale: bool


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    title: str | None = Field(
        default=None,
        description="What the reader named it. Null means they have not; show the filename.",
    )
    size_bytes: int
    created_at: str
    version: str | None = None
    page_count: int = 0
    segment_count: int = 0
    reading: ReadingPosition | None = Field(
        default=None, description="Null when this reader has never opened the book."
    )

    @classmethod
    def of(cls, document: Document, *, progress: Progress | None = None) -> DocumentSummary:
        return cls(
            document_id=document.document_id,
            filename=document.filename,
            title=document.title,
            size_bytes=document.size_bytes,
            created_at=document.created_at,
            version=document.version,
            page_count=document.page_count,
            segment_count=document.segment_count,
            reading=(
                ReadingPosition(
                    segment_id=progress.segment_id,
                    segment_index=progress.segment_index,
                    updated_at=progress.updated_at,
                    stale=(
                        document.version is not None
                        and document.version != progress.document_version
                    ),
                )
                if progress is not None
                else None
            ),
        )


class DocumentDetail(DocumentSummary):
    notes: list[str] = Field(
        default_factory=list, description="What this document lost, across all pages."
    )
    job: JobStatus | None = None

    @classmethod
    def of(
        cls, document: Document, job: Job | None = None, *, progress: Progress | None = None
    ) -> DocumentDetail:
        return cls(
            **DocumentSummary.of(document, progress=progress).model_dump(),
            notes=list(document.notes),
            job=JobStatus.of(job) if job else None,
        )


class AudioManifest(BaseModel):
    """What produced a segment's audio, without downloading it."""

    # "model_version" is the right name for this field — it is the version of
    # the TTS model — and pydantic reserves the "model_" prefix for its own
    # methods. Releasing the namespace is better than renaming the field to
    # something less accurate.
    model_config = ConfigDict(protected_namespaces=())

    segment_id: str
    cache_key: str
    generated: bool
    real_model: bool = Field(
        description=(
            "False means a placeholder tone, not speech. It must never be presented as narration."
        )
    )
    voice_id: str | None = None
    model_version: str | None = None
    duration_seconds: float | None = None


class ProgressBody(BaseModel):
    segment_id: str
    offset_seconds: float = Field(default=0.0, ge=0.0)


class ProgressDetail(BaseModel):
    document_id: str
    segment_id: str
    offset_seconds: float
    document_version: str
    updated_at: str
    segment_index: int = Field(
        default=0, description="How far into the book, resolved when the position was saved."
    )
    stale: bool = Field(
        description=(
            "True when the document has been reprocessed since this position was saved. "
            "The segment may no longer be where the reader left off."
        )
    )

    @classmethod
    def of(cls, progress: Progress, *, current_version: str | None) -> ProgressDetail:
        return cls(
            document_id=progress.document_id,
            segment_id=progress.segment_id,
            offset_seconds=progress.offset_seconds,
            document_version=progress.document_version,
            updated_at=progress.updated_at,
            segment_index=progress.segment_index,
            stale=current_version is not None and current_version != progress.document_version,
        )


#: The longest note a reader may attach to a bookmark. Long enough for a
#: sentence about why they marked it, short enough that a list of them can be
#: listened to — and short enough that this is a label rather than somewhere a
#: whole document gets pasted.
MAX_NOTE = 280


class BookmarkBody(BaseModel):
    segment_id: str
    note: str | None = Field(
        default=None,
        max_length=MAX_NOTE,
        description="The reader's own words. Optional: marking the place is the point.",
    )


class BookmarkDetail(BaseModel):
    """A bookmark, with enough of the page to announce it without opening it.

    The sentence is read out of the document as it stands now rather than
    copied when the bookmark was made. That way a list of bookmarks cannot
    describe a passage the book no longer contains — and the book's text stays
    in one place, so deleting the document really does delete it.
    """

    bookmark_id: str
    document_id: str
    segment_id: str
    note: str | None = None
    created_at: str
    document_version: str
    stale: bool = Field(
        description=(
            "True when the document has been reprocessed since this bookmark was made. "
            "It may no longer point where the reader put it."
        )
    )
    segment_found: bool = Field(
        description=(
            "False when this bookmark's segment is not in the document as it stands. "
            "The page and text are then absent rather than guessed at."
        )
    )
    page_index: int | None = None
    page_label: str | None = Field(
        default=None,
        description="The page number as printed, when the book declares one.",
    )
    display_text: str | None = Field(
        default=None, description="The sentence this bookmark marks, for announcing the list."
    )

    @classmethod
    def of(
        cls,
        bookmark: Bookmark,
        *,
        segment: ReadableSegment | None,
        current_version: str | None,
    ) -> BookmarkDetail:
        return cls(
            bookmark_id=bookmark.bookmark_id,
            document_id=bookmark.document_id,
            segment_id=bookmark.segment_id,
            note=bookmark.note,
            created_at=bookmark.created_at,
            document_version=bookmark.document_version,
            stale=current_version is not None and current_version != bookmark.document_version,
            segment_found=segment is not None,
            page_index=segment.page_index if segment else None,
            page_label=segment.page_label if segment else None,
            display_text=segment.display_text if segment else None,
        )


# A question is a request for help with one private book, not a place to paste
# another book. The bound keeps a single request cheap enough to answer and the
# browser's live-region response comprehensible.
MAX_QUESTION = 500


class RenameBody(BaseModel):
    """A reader's own name for a book.

    Bounded because it is displayed and announced, not because storage cares.
    Whitespace-only is rejected by the endpoint, which treats it as "clear the
    name" rather than as a title made of spaces.
    """

    title: str = Field(max_length=200)


class QuestionBody(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


class StudyCitation(BaseModel):
    """The exact source and place supporting an extractive answer."""

    passage_id: str
    page_index: int
    page_label: str | None = None
    section: str = ""
    segment_ids: list[str] = Field(default_factory=list)
    quote: str


class StudyAnswer(BaseModel):
    """A document-grounded answer, or an explicit abstention."""

    document_id: str
    answer: str | None = Field(
        default=None,
        description=(
            "An exact passage from the document. Null when the document does not support an answer."
        ),
    )
    citations: list[StudyCitation] = Field(default_factory=list)
    abstained: bool
