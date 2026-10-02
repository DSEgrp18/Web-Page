"""Which retriever this process uses for study answers and in-book search."""

from __future__ import annotations

import os

from sinhala_documents.retrieval_select import MODES, RETRIEVAL_VERSION

RETRIEVAL_ENV = "SINHALA_READER_RETRIEVAL"


def retrieval_mode() -> str:
    mode = os.environ.get(RETRIEVAL_ENV, "").strip().lower() or "lexical"
    if mode not in MODES:
        raise ValueError(
            f"{RETRIEVAL_ENV}={mode!r} is not a retriever this server knows. "
            f"Use one of: {', '.join(MODES)}."
        )
    return mode


def retrieval_note() -> str:
    return f"Study retrieval is {retrieval_mode()} ({RETRIEVAL_VERSION})."
