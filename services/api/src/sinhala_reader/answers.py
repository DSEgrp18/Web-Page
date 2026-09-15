"""Which answerer study mode uses, chosen once from configuration.

The same shape as :mod:`.structure` and :mod:`.adapters`, and for the same
reason: what a deployment gets should be a setting, not an edit to a source file.

The default is extractive, and that is not merely a safe default. The extractive
answerer needs no provider, no key, and no network, so it is what runs when the
generative one is unavailable, unaffordable, or wrong — and it is what makes the
whole feature shippable without a contract with Google.

An unrecognised value stops the process rather than quietly falling back, which
is how the voice and the structure source behave and for the same reason: a typo
in a deployment variable must not silently change what readers get.
"""

from __future__ import annotations

import os

from sinhala_documents.answering import AnswerAdapter, ExtractiveAnswerer
from sinhala_documents.gemini_answers import GeminiAnswerer

#: Which answerer to use. See :data:`MODES`.
ANSWERS_ENV = "SINHALA_READER_ANSWERS"

EXTRACTIVE = "extractive"
GEMINI = "gemini"
MODES = (EXTRACTIVE, GEMINI)


def answers_mode() -> str:
    """The configured mode, defaulting to the book's own words."""
    return os.environ.get(ANSWERS_ENV, "").strip().lower() or EXTRACTIVE


def build_answerer() -> AnswerAdapter:
    """Build the answerer this process will use.

    Raises:
        ValueError: if the mode is not one of :data:`MODES`. Deliberately fatal.
    """
    mode = answers_mode()
    if mode == EXTRACTIVE:
        return ExtractiveAnswerer()
    if mode == GEMINI:
        return GeminiAnswerer()
    raise ValueError(
        f"{ANSWERS_ENV}={mode!r} is not an answerer this server knows. "
        f"Use one of: {', '.join(MODES)}."
    )


def answer_limitations() -> list[str]:
    """What a deployment should know about the answer setting, for readiness.

    Both entries are statements about what a reader will be handed, not warnings
    that something is broken. They are different claims — "the book says this"
    and "a model wrote this from the book" — and a deployment deserves to see
    which one it is serving.
    """
    if answers_mode() == GEMINI:
        return [
            "Study answers are written by an external model, which means the "
            "passages retrieved for each question are sent to Google. Answers are "
            "the model's words, not the book's, and are labelled as such. Cited "
            "passages are checked to be ones actually retrieved, so a citation "
            "cannot be invented; the prose itself is not verified and can be wrong.",
        ]
    return [
        "Study answers are extracts from the book, never written prose. They are "
        "always the document's own words, and the answerer abstains whenever the "
        "question's wording does not match the text — which is often. Set "
        f"{ANSWERS_ENV}=gemini for written Sinhala answers.",
    ]
