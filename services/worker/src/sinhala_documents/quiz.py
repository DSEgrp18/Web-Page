"""Practice questions: the verifier every question must pass, and a generator
that needs no model.

CLAUDE.md, "Generated questions": a model may write a question, but it may never
be the only judge of its answer. :func:`verify` is that judge. It is
deterministic, it is shared by every generator, and **one failed check
discards the question** — it is never repaired.

:func:`cloze_questions` is the generator that needs no provider: the book's own
sentence with one term taken out. It must stay good enough to ship on its own,
because it is what runs when a model is unavailable, unaffordable or wrong.

Framework-free, like the rest of this package: no web framework, no model
client, nothing but the text.
"""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .retrieval import LexicalIndex, tokenize

#: Bump when a check changes: it is recorded on every quiz.
VERIFIER_VERSION = "1"

#: Bump when the cloze generator's choices change.
#: 2: the blank is a term the book returns to, distractors are words the book
#: uses more than once, and sentences that lean on "this" or "it" are skipped.
CLOZE_VERSION = "2"

#: What stands in for the missing term.
BLANK = "_____"

#: Options per question: the answer and three distractors.
OPTIONS = 4


class Rejection(StrEnum):
    """Why a candidate question was discarded. Counted in evaluation (RQ1)."""

    UNKNOWN_PASSAGE = "unknown_passage"
    PAGE_NOT_ACCEPTED = "page_not_accepted"
    EMPTY = "empty"
    TOO_FEW_OPTIONS = "too_few_options"
    OPTIONS_NOT_DISTINCT = "options_not_distinct"
    BAD_ANSWER_INDEX = "bad_answer_index"
    QUOTE_NOT_IN_PASSAGE = "quote_not_in_passage"
    ANSWER_NOT_IN_QUOTE = "answer_not_in_quote"
    DISTRACTOR_IN_QUOTE = "distractor_in_quote"
    ANSWER_IN_QUESTION = "answer_in_question"


@dataclass(frozen=True)
class SourcePassage:
    """A numbered passage a generator was given, and whether its page may ground
    a question. A page that needs review, or that a teacher withheld, never does."""

    number: int
    text: str
    page_index: int
    page_label: str | None
    segment_ids: tuple[str, ...]
    accepted: bool = True


@dataclass(frozen=True)
class Candidate:
    """A question as a generator proposes it, before the verifier has ruled."""

    question: str
    options: tuple[str, ...]
    answer: int
    passage: int
    """The number of the passage cited as evidence."""
    quote: str
    """The evidence, which must appear verbatim in that passage."""
    segment_id: str | None = None
    """Where "hear the source" goes, when the generator knows the sentence."""


_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """For comparison only: NFC, one space, Latin letters folded.

    The zero-width joiner and non-joiner are kept. They are part of Sinhala
    words: stripping them would make two different spellings compare equal,
    and a quote "match" that is not one.
    """
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip().casefold()


def verify(candidate: Candidate, passages: dict[int, SourcePassage]) -> Rejection | None:
    """``None`` if the question may stand; otherwise the first reason it may not.

    Every check is mandatory. A caller never repairs a rejected question: it
    discards it, and may ask its generator for another.
    """
    source = passages.get(candidate.passage)
    if source is None:
        return Rejection.UNKNOWN_PASSAGE
    if not source.accepted:
        return Rejection.PAGE_NOT_ACCEPTED
    question = normalise(candidate.question)
    options = [normalise(option) for option in candidate.options]
    quote = normalise(candidate.quote)
    if not question or not quote or any(not option for option in options):
        return Rejection.EMPTY
    if len(options) < OPTIONS:
        return Rejection.TOO_FEW_OPTIONS
    if len(set(options)) != len(options):
        return Rejection.OPTIONS_NOT_DISTINCT
    if not 0 <= candidate.answer < len(options):
        return Rejection.BAD_ANSWER_INDEX
    if quote not in normalise(source.text):
        return Rejection.QUOTE_NOT_IN_PASSAGE
    answer = options[candidate.answer]
    if answer not in quote:
        return Rejection.ANSWER_NOT_IN_QUOTE
    if any(option in quote for i, option in enumerate(options) if i != candidate.answer):
        return Rejection.DISTRACTOR_IN_QUOTE
    if answer in question:
        return Rejection.ANSWER_IN_QUESTION
    return None


@dataclass(frozen=True)
class Sentence:
    """One sentence of the book, and the passage it belongs to."""

    passage: int
    segment_id: str
    text: str


#: Shortest term worth blanking, in characters. Shorter Sinhala tokens are
#: mostly particles and case endings, which test grammar, not the book.
MIN_TERM = 4

#: A word must occur at least this often in the book to be blanked or offered
#: as a distractor. A word the book uses once is as likely to be an extraction
#: fault as a term (a stray "විට්න්" among real options gives the answer away),
#: and a term the lesson is about comes back.
MIN_OCCURRENCES = 2

#: Words that point back to an earlier sentence. A sentence that opens with one
#: ("මේ ගැන", "එය") cannot be understood alone, so it makes a question the
#: student cannot answer from what they are shown.
_POINTS_BACK = frozenset(
    {
        "මේ", "මෙම", "මෙය", "මේවා", "මෙහි", "මෙසේ",
        "ඒ", "එම", "එය", "ඒවා", "එහි", "එසේ", "එබැවින්", "එනිසා", "එහෙයින්",
        "ඔහු", "ඇය", "ඔවුහු", "ඔවුන්", "ඔවුන්ගේ", "ඔහුගේ", "ඇයගේ",
    }
)  # fmt: skip

#: How far into a sentence a pointing-back word makes it depend on another.
_LEADING_TOKENS = 4

#: Sentences outside these bounds make poor questions: too short to carry a
#: fact, or too long to hold in mind while listening to the options.
MIN_SENTENCE = 40
MAX_SENTENCE = 260


def _is_term(token: str) -> bool:
    return len(token) >= MIN_TERM and not any(character.isdigit() for character in token)


def _stands_alone(text: str) -> bool:
    """Whether a sentence can be understood without the one before it."""
    if not MIN_SENTENCE <= len(text) <= MAX_SENTENCE:
        return False
    return not any(token in _POINTS_BACK for token in tokenize(text)[:_LEADING_TOKENS])


def _seeded(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))


def cloze_questions(
    sentences: Sequence[Sentence],
    index: LexicalIndex,
    *,
    seed: str,
    limit: int = 10,
    first: Sequence[int] = (),
    occurrences: Counter[str] | None = None,
) -> list[Candidate]:
    """Fill-in-the-blank candidates from the book's own sentences.

    The blank is the sentence's **key term**: a word that recurs in the book
    but not everywhere, weighted by how often it comes back and how rare it is
    across passages (the measure retrieval ranks by). The rarest word alone
    picked adverbs and extraction faults. Distractors are other recurring terms
    of similar length, preferring the same ending, so the options read alike
    and the answer cannot be guessed from its grammar. Sentences that lean on
    an earlier one are skipped.

    ``occurrences`` counts words across the whole book, when ``sentences`` is
    only the part a student chose: whether a word recurs is a fact about the
    book, not about the part. Without it, the sentences given are counted.

    ``first`` lists sentences to use before the rest, in that order — those
    matching the topic a student asked about. Otherwise the order is shuffled.
    Deterministic for a given seed: the same book makes the same quiz.

    These are candidates. The caller still runs :func:`verify` on each.
    """
    counts = Counter(token for sentence in sentences for token in tokenize(sentence.text))
    if occurrences is not None:
        counts = occurrences

    def is_key(token: str) -> bool:
        return _is_term(token) and index.is_informative(token) and counts[token] >= MIN_OCCURRENCES

    vocabulary = sorted({token for s in sentences for token in tokenize(s.text) if is_key(token)})
    picked: list[Candidate] = []
    rng = _seeded(seed)
    order = list(range(len(sentences)))
    rng.shuffle(order)
    if first:
        preferred = [position for position in first if 0 <= position < len(sentences)]
        order = preferred + [position for position in order if position not in set(preferred)]
    for position in order:
        if len(picked) >= limit:
            break
        sentence = sentences[position]
        if not _stands_alone(sentence.text):
            continue
        tokens = [t for t in tokenize(sentence.text) if is_key(t)]
        if not tokens:
            continue
        term = max(tokens, key=lambda t: (counts[t] * index.idf(t), t))
        blanked, count = re.subn(re.escape(term), BLANK, sentence.text, count=1, flags=re.I)
        if count != 1:
            continue
        distractors = _distractors(term, sentence.text, vocabulary, _seeded(f"{seed}|{position}"))
        if len(distractors) < OPTIONS - 1:
            continue
        options = [term, *distractors]
        _seeded(f"{seed}|{sentence.segment_id}").shuffle(options)
        picked.append(
            Candidate(
                question=blanked,
                options=tuple(options),
                answer=options.index(term),
                passage=sentence.passage,
                quote=sentence.text,
                segment_id=sentence.segment_id,
            )
        )
    return picked


def _distractors(
    term: str, sentence: str, vocabulary: Iterable[str], rng: random.Random
) -> list[str]:
    in_sentence = normalise(sentence)
    near = [
        word
        for word in vocabulary
        if word != term
        and normalise(word) not in in_sentence
        and abs(len(word) - len(term)) <= max(2, len(term) // 3)
        # Neither may contain the other: "ජාලය" beside "ජාල" is a giveaway.
        and word not in term
        and term not in word
    ]
    rng.shuffle(near)
    # Same ending first: case endings should not give the answer away.
    near.sort(key=lambda word: word[-2:] != term[-2:])
    return near[: OPTIONS - 1]
