"""Which kind of answer study mode gives, behind one small interface.

Two answerers exist, and the difference between them is not a quality setting —
it is a difference in what a reader is being handed.

:class:`ExtractiveAnswerer` returns the book's own sentences. Every word is
attributable to the document. It cannot explain, summarise, or answer a question
whose wording does not overlap the text, and it abstains far more often than a
reader expects.

:class:`~.gemini_answers.GeminiAnswerer` writes a Sinhala answer from retrieved
passages. It is far more useful and it is a model's words, which CLAUDE.md
permits for study mode and *only* for study mode: read mode narrates the
document and a model must never supply the words a reader hears as the book.

So :class:`Answer` carries ``generated``. It is not decoration. The interface
labels the two differently because a blind reader cannot see which they got, and
"the book says" and "a model wrote this from the book" are different claims.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .answerer import Answer, answer_question
from .passages import Passage

log = logging.getLogger(__name__)


class AnswerUnavailable(RuntimeError):
    """The answerer could not be reached or could not be trusted.

    Raised for every failure with the same meaning: no key, no network, a rate
    limit, a timeout, a malformed reply. The caller's response to all of them is
    the same — fall back to the extractive answer — so distinguishing them here
    would only invite retrying the ones that will never succeed.
    """


class AnswerAdapter(ABC):
    """Turn a question and some retrieved passages into an answer."""

    @abstractmethod
    def answer(self, question: str, passages: tuple[Passage, ...]) -> Answer: ...

    @property
    @abstractmethod
    def version(self) -> str:
        """What produced the answer, for provenance."""


class ExtractiveAnswerer(AnswerAdapter):
    """The book's own words, or nothing.

    The path that must keep working: it needs no provider, no key, and no
    network, and it is what runs when the generative one is unavailable,
    unaffordable, or wrong.
    """

    @property
    def version(self) -> str:
        return "extractive/1"

    def answer(self, question: str, passages: tuple[Passage, ...]) -> Answer:
        return answer_question(question, passages)


def answer_with_fallback(
    adapter: AnswerAdapter,
    fallback: AnswerAdapter,
    question: str,
    passages: tuple[Passage, ...],
) -> Answer:
    """Ask `adapter`, and fall back rather than fail.

    A study answer is not worth a 500. If the provider is down, rate-limited, or
    returns something unusable, the reader gets the extractive answer — which is
    less useful but true — instead of an error they cannot act on.

    The failure is **logged**, because silence here is its own bug: a deployment
    paying for a provider and quietly serving extracts instead has no way to
    find out. The reason is logged; the question is not, since CLAUDE.md forbids
    logging private content by default and a question is a reader's own words.
    """
    try:
        return adapter.answer(question, passages)
    except AnswerUnavailable as reason:
        log.warning(
            "Falling back to the extractive answerer: %s (%s could not answer)",
            reason,
            adapter.version,
        )
        return fallback.answer(question, passages)
