"""A held-out book, prepared the way the product prepares it, run locally.

The evaluation reads the same passages the product would: the worker's own
pipeline, with no server, no account and nothing sent anywhere.
"""

from __future__ import annotations

from pathlib import Path

from sinhala_documents import prepare_document
from sinhala_documents.model import QualityState
from sinhala_documents.passages import Passage, build_passages
from sinhala_documents.pipeline import ReadableDocument
from sinhala_documents.quiz import SourcePassage


def prepare(path: Path) -> ReadableDocument:
    return prepare_document(path.read_bytes(), filename=path.name)


def passages(document: ReadableDocument) -> list[Passage]:
    return build_passages(document)


def source_passages(document: ReadableDocument) -> list[SourcePassage]:
    """Numbered from 1, as a generator sees them. Only a cleanly read page grounds
    a question here: there is no teacher review in an offline evaluation run."""
    accepted = {p.page_index for p in document.pages if p.quality is QualityState.ACCEPTED}
    return [
        SourcePassage(
            number=number,
            text=passage.text,
            page_index=passage.page_index,
            page_label=passage.page_label,
            segment_ids=passage.segment_ids,
            accepted=passage.page_index in accepted,
        )
        for number, passage in enumerate(passages(document), start=1)
    ]
