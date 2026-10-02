"""Which retriever study mode uses, chosen once from configuration."""

from __future__ import annotations

from typing import Protocol

from .dense_retrieval import DenseIndex, HybridIndex
from .passages import Passage
from .retrieval import LexicalIndex

MODES = ("lexical", "dense", "hybrid")
RETRIEVAL_VERSION = "1"


class SearchIndex(Protocol):
    document_version: str | None

    def search(self, question: str, *, limit: int = 5) -> tuple: ...


def build_index(passages: tuple[Passage, ...] | list[Passage], mode: str) -> SearchIndex:
    if mode == "lexical":
        return LexicalIndex(passages)
    if mode == "dense":
        return DenseIndex(passages)
    if mode == "hybrid":
        return HybridIndex(passages)
    raise ValueError(f"Unknown retrieval mode {mode!r}. Use lexical, dense, or hybrid.")
