"""Finding the passages that could answer a question.

CLAUDE.md requires lexical, dense and hybrid retrieval to be **compared**, and
the choice made by measurement rather than by reputation — multilingual claims
do not establish Sinhala quality. This is the lexical arm, and it is first for
three reasons that are not about it being best:

* It needs no provider, no key, no quota and no network, so it is the arm that
  still works when everything else is rate-limited.
* It is the baseline anything else has to beat. Adopting embeddings without one
  means never learning whether they helped.
* It is inspectable. When it retrieves the wrong passage you can see the term
  that did it, which is not true of a vector you cannot read.

One document at a time, by construction
---------------------------------------
An index belongs to a single document. Not by a filter that could be forgotten,
but because the index is built from one document's passages and holds nothing
else, so there is no query that can reach another reader's book. CLAUDE.md
requires authorization enforced before results reach the LLM, and the surest
enforcement is a structure in which the leak has nowhere to come from. It also
matches the product: answers are grounded in the book you opened.

Retrieval cannot decide abstention, and must not pretend to
-----------------------------------------------------------
A non-empty result is **not** evidence that the document addresses the question,
and no amount of work here will make it one. This refuses to return a passage
matched on nothing but terms common to the whole document, which removes the
crudest false positives — but it is a floor, not a judgement, and a question
made of words the book happens not to use often will still retrieve something.

Measured on the real textbook: a question about computer network security
returned three history passages, matched on "do" and "description". Nothing in a
ranking function can tell that those passages are irrelevant; only reading them
can.

So whether the retrieved passages actually support an answer is the **answerer's**
decision, made with the passages in hand, and CLAUDE.md puts the obligation to
abstain there. A retriever that promised otherwise would be the most dangerous
component in this system.

What lexical retrieval will not do for Sinhala, stated plainly
--------------------------------------------------------------
Sinhala is heavily inflected, and this matches whole words. A question asking
about කර්මාන්තය will not match කර්මාන්තයේ, which is the same word in another
case. No stemmer is applied, because a wrong stemmer silently merges words that
differ and there is no Sinhala stemmer here anybody has evaluated. This is the
single strongest argument for measuring a dense arm, and the reason this module
does not claim to be the answer.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .passages import Passage

#: The zero-width joiner is part of a word, not a boundary. It sits *inside*
#: Sinhala conjuncts, so splitting on it turns one word into two that match
#: nothing.
_JOINER = "‍"


def _is_word_character(character: str) -> bool:
    r"""Whether this character is part of a word.

    Written against Unicode categories rather than ``\w``, because Python's
    ``\w`` does **not** include combining marks — and Sinhala vowel signs and
    the virama are combining marks. With ``\w`` the word දුම්රිය tokenises as
    ද, ම, ර, ය: four meaningless letter fragments instead of one word. Every
    query would then match on fragments shared by half the book, and no query
    would ever match a whole word.

    The failure is quiet, which is what makes it dangerous: retrieval still
    returns results, ranked by nonsense.
    """
    return character == _JOINER or unicodedata.category(character)[0] in {"L", "M", "N"}


#: Standard BM25 constants. Not tuned: tuning them against no evaluation set
#: would be fitting to nothing.
K1 = 1.2
B = 0.75

#: A term appearing in more than this fraction of a document's passages cannot
#: distinguish between them, so it may contribute to *ranking* but may not be
#: the only reason a passage is returned at all.
#:
#: A structural rule rather than a tuned threshold: a term in most passages
#: cannot tell them apart. Still a starting point for evaluation to move.
#:
#: It does **not** solve the case that prompted it, and that is worth writing
#: down. Asked "පරිගණක ජාල ආරක්ෂාව පිළිබඳ විස්තර කරන්න" - computer network
#: security - over sixteen pages of a history textbook, BM25 returned three
#: passages matching only "කරන්න" (do) and "විස්තර" (description). Those words
#: are *rare* in a history book, so document frequency calls them informative,
#: and the rule lets them through. What makes them useless is that they are
#: question words, which frequency cannot see.
#:
#: Fixing that needs a Sinhala stopword list, and there is no evaluated one
#: here. Inventing one would be exactly the guesswork this project avoids, so
#: it waits for the evaluation set - and until then, abstention rests where the
#: section above puts it.
COMMON_TERM_FRACTION = 0.5


def tokenize(text: str) -> list[str]:
    """Words, for matching. Not for display and not for speech."""
    tokens: list[str] = []
    current: list[str] = []
    for character in text:
        if _is_word_character(character):
            current.append(character)
        elif current:
            tokens.append("".join(current).lower())
            current = []
    if current:
        tokens.append("".join(current).lower())
    return tokens


@dataclass(frozen=True)
class Hit:
    """A passage that might answer the question, and how well it matched."""

    passage: Passage
    score: float
    terms: tuple[str, ...] = ()
    """The query terms that actually matched, strongest first.

    Kept so a wrong answer can be explained. A retrieval you cannot explain is
    one you can only replace, never fix.
    """


class LexicalIndex:
    """BM25 over one document's passages."""

    def __init__(self, passages: tuple[Passage, ...] | list[Passage]) -> None:
        self._passages = tuple(passages)
        self._tokens = [tokenize(p.text) for p in self._passages]
        self._lengths = [len(t) for t in self._tokens]
        self._average = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._frequencies = [Counter(t) for t in self._tokens]

        documents = Counter()
        for tokens in self._tokens:
            documents.update(set(tokens))
        total = len(self._passages)
        # The +0.5 smoothing keeps the idf of a term appearing in every passage
        # small and positive rather than negative, which would make a passage
        # score *worse* for containing a word the question used.
        self._idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in documents.items()
        }
        #: Terms rare enough to mean something here. A match on nothing but
        #: common terms is not a match; see :data:`COMMON_TERM_FRACTION`.
        ceiling = max(1, int(total * COMMON_TERM_FRACTION))
        self._informative = {term for term, count in documents.items() if count <= ceiling}

    @property
    def document_version(self) -> str | None:
        """The version these passages came from.

        A caller holding an index built from superseded text is holding an index
        that will cite passages which no longer exist, so the version is exposed
        rather than assumed.
        """
        return self._passages[0].document_version if self._passages else None

    def search(self, question: str, *, limit: int = 5) -> tuple[Hit, ...]:
        """The passages most likely to contain the answer, best first.

        Returns fewer than ``limit`` when fewer match at all, and nothing when
        none do. An empty result is a real answer: it is what the caller needs
        in order to abstain rather than to answer from whatever ranked highest
        among things that matched nothing.
        """
        terms = tokenize(question)
        if not terms or not self._passages:
            return ()

        hits: list[Hit] = []
        for index, passage in enumerate(self._passages):
            frequencies = self._frequencies[index]
            length = self._lengths[index] or 1
            score = 0.0
            matched: list[tuple[float, str]] = []
            informative = False
            for term in set(terms):
                count = frequencies.get(term, 0)
                if not count:
                    continue
                idf = self._idf.get(term, 0.0)
                contribution = idf * (
                    count * (K1 + 1) / (count + K1 * (1 - B + B * length / (self._average or 1)))
                )
                score += contribution
                matched.append((contribution, term))
                informative = informative or term in self._informative
            if score > 0 and informative:
                matched.sort(reverse=True)
                hits.append(Hit(passage=passage, score=score, terms=tuple(t for _, t in matched)))

        hits.sort(key=lambda hit: (-hit.score, hit.passage.page_index))
        return tuple(hits[:limit])
