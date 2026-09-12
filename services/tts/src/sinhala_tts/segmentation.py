"""Split document text into sentence-sized pieces the model can speak.

Segmentation is where a reader is won or lost. Cut in the wrong place and the
narration pauses mid-clause; cut too rarely and the model runs past its limit
and truncates a sentence with nothing to say it did. It also decides what
"sentence" means for highlighting and for resume, so the boundaries have to be
stable, not incidental.

Three rules shape this:

* **Bound by the model's real limit, in the units the model uses.** The limit is
  250 characters of *model input* — after normalisation and romanisation —
  because that is the string the tokenizer sees. Counting the original Sinhala
  would measure the wrong thing: ``to_ascii`` changes length substantially.
* **Never split inside a word.** Every fallback ends at a word boundary; a
  segment that begins mid-word is not recoverable by a listener.
* **Keep offsets into the original text.** Highlighting, resume, and citations
  all need to point back at what the reader can see, not at the romanised form
  they cannot.

Sentence detection is structural rather than a list of known abbreviations. A
full stop ends a sentence only when it is followed by whitespace or the end of
the text, and is not a decimal point, an initial, part of a dotted abbreviation
like ``අ.පො.ස.``, or inside something like a filename. That handles far more
than a word list would, and does not quietly fail on the abbreviation nobody
thought to add.

The one place a word list is unavoidable is a *single* abbreviation followed by
a space, such as ``රු.`` before an amount. That list is short, marked, and
**needs a native speaker's review** — like the number words, it is a claim about
Sinhala rather than about code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .normalize import (
    MODEL_INPUT_CHAR_LIMIT,
    NumberStyle,
    is_speakable,
    to_model_input,
    to_speech_text,
)

#: Characters that can end a sentence. Sinhala uses the Latin full stop; the
#: Sinhala-specific kunddaliya (U+0DF4) is archaic but appears in older texts.
SENTENCE_TERMINATORS = ".!?…෴"

#: Abbreviations that end in a full stop and are normally followed by a space,
#: so the structural rules cannot tell them from a sentence end.
#:
#: **Needs review by a native Sinhala speaker.** Anything missing here causes a
#: spurious split — an audible pause mid-sentence, not lost text — so the
#: failure is mild and visible rather than silent.
ABBREVIATIONS_BEFORE_SPACE = frozenset(
    {
        "රු",  # රුපියල්, rupees, before an amount
        "අංක",  # number, before a figure
        "පි",  # පිටුව, page, before a figure
        "ආචාර්ය",  # Dr
        "මහාචාර්ය",  # Prof
        "No",
        "Fig",
        "Dr",
        "Mr",
        "Mrs",
        "Ms",
        "Prof",
        "etc",
        "vs",
    }
)


@dataclass(frozen=True)
class Segment:
    """One synthesisable piece of a document.

    ``display_text`` is a slice of the original text and is what a reader sees
    and what highlighting points at. ``spoken_text`` is the normalised Sinhala,
    readable and reviewable. ``model_text`` is the romanised ASCII the model is
    given and is meaningful to nothing else.
    """

    segment_id: str
    index: int
    display_text: str
    spoken_text: str
    model_text: str
    start_offset: int
    end_offset: int

    @property
    def is_speakable(self) -> bool:
        """False for a segment with nothing to say — a rule of dashes, say.

        Kept in the sequence rather than dropped, so offsets and indices still
        line up with the document, but never sent for synthesis.
        """
        return is_speakable(self.model_text)

    @property
    def model_length(self) -> int:
        return len(self.model_text)


def _is_sentence_end(text: str, position: int) -> bool:
    """Whether the terminator at ``position`` actually ends a sentence."""
    character = text[position]

    # Must be followed by whitespace or nothing. This alone rules out decimals
    # (3.14), filenames (report.pdf), and the internal dots of අ.පො.ස.
    after = text[position + 1 :]
    if after and not after[0].isspace():
        return False

    if character != ".":
        return True

    before = text[:position]
    # The token immediately before the dot, back to the previous whitespace.
    token = before.rsplit(None, 1)[-1] if before.strip() else ""

    # A dotted cluster like අ.පො.ස or U.S.A: the dots inside it were already
    # rejected above, and the final one belongs to the abbreviation.
    if "." in token:
        return False

    # A single character before the dot is an initial, as in "A. B. Silva".
    if len(token) == 1 and not token.isdigit():
        return False

    return token not in ABBREVIATIONS_BEFORE_SPACE


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of each sentence in the original text, whitespace trimmed."""
    spans: list[tuple[int, int]] = []
    start = 0
    for position, character in enumerate(text):
        if character in SENTENCE_TERMINATORS and _is_sentence_end(text, position):
            spans.append((start, position + 1))
            start = position + 1
    if start < len(text):
        spans.append((start, len(text)))

    trimmed = []
    for span in spans:
        begin, end = _trim(text, *span)
        if end > begin:
            trimmed.append((begin, end))
    return trimmed


def _trim(text: str, begin: int, end: int) -> tuple[int, int]:
    """Shrink a span past surrounding whitespace.

    Applied everywhere a span is produced, including the recursive base case.
    Missing it there let a segment begin with the space it was split on, which
    is invisible in the text and wrong in the offsets.
    """
    chunk = text[begin:end]
    lead = len(chunk) - len(chunk.lstrip())
    tail = len(chunk) - len(chunk.rstrip())
    return begin + lead, max(begin + lead, end - tail)


def _split_oversized(
    text: str,
    begin: int,
    end: int,
    limit: int,
    *,
    numbers: NumberStyle = NumberStyle.PROSE,
) -> list[tuple[int, int]]:
    """Break a sentence that is too long for the model into smaller spans.

    Prefers a clause boundary — a comma, semicolon or colon — and falls back to
    a word boundary. Never splits inside a word: a segment starting mid-word is
    not something a listener can recover from.

    Works by bisecting on the *display* text and re-measuring the model text
    each time, because the relationship between the two is not proportional.
    Romanisation lengthens some Sinhala substantially and barely touches others.
    """
    begin, end = _trim(text, begin, end)
    if begin >= end:
        return []
    if len(to_model_input(text[begin:end], numbers=numbers)) <= limit:
        return [(begin, end)]

    # Longest prefix whose model text still fits. Bisecting rather than
    # estimating, since characters of Sinhala do not map to a fixed number of
    # romanised characters.
    low, high = begin + 1, end
    best = begin + 1
    while low <= high:
        middle = (low + high) // 2
        if len(to_model_input(text[begin:middle], numbers=numbers)) <= limit:
            best = middle
            low = middle + 1
        else:
            high = middle - 1

    window = text[begin:best]
    cut = max(window.rfind(","), window.rfind(";"), window.rfind(":"), window.rfind("،"))
    if cut > 0:
        cut = begin + cut + 1
    else:
        space = window.rfind(" ")
        # No boundary at all inside the window: a single unbroken run longer
        # than the limit. Cut at the measured point rather than emitting
        # something the model will truncate silently.
        cut = begin + space if space > 0 else best

    if cut <= begin:
        cut = best

    first = _trim(text, begin, cut)
    rest = _split_oversized(text, cut, end, limit, numbers=numbers) if cut < end else []
    return ([first] if first[1] > first[0] else []) + rest


def _segment_id(index: int, model_text: str) -> str:
    """Stable identity for highlighting, resume, and cache lookups.

    Derived from the content as well as the position, so a segment keeps its id
    when text elsewhere in the document changes, and gets a new one when its own
    text changes — which is what should invalidate its audio.
    """
    digest = hashlib.sha256(model_text.encode("utf-8")).hexdigest()[:8]
    return f"{index:04d}-{digest}"


def segment_text(
    text: str,
    *,
    limit: int = MODEL_INPUT_CHAR_LIMIT,
    numbers: NumberStyle = NumberStyle.PROSE,
) -> list[Segment]:
    """Split document text into segments the model can speak.

    Every returned segment's ``model_text`` is within ``limit``, so the caller
    never has to guard against it. Segments with nothing speakable are returned
    with ``is_speakable`` False rather than dropped, so indices and offsets
    still describe the document.

    ``numbers`` travels all the way through rather than being applied at the
    end, because it changes the *length* of the model text and the limit is
    measured against that: "65" is two words as a quantity and three digits read
    singly, and a segment sized under one reading can exceed the model's limit
    under the other.
    """
    if not text.strip():
        return []

    spans: list[tuple[int, int]] = []
    for begin, end in _sentence_spans(text):
        spans.extend(_split_oversized(text, begin, end, limit, numbers=numbers))

    segments: list[Segment] = []
    for index, (begin, end) in enumerate(spans):
        display = text[begin:end]
        model_text = to_model_input(display, numbers=numbers)
        segments.append(
            Segment(
                segment_id=_segment_id(index, model_text),
                index=index,
                display_text=display,
                spoken_text=to_speech_text(display, numbers=numbers),
                model_text=model_text,
                start_offset=begin,
                end_offset=end,
            )
        )
    return segments


def speakable(segments: list[Segment]) -> list[Segment]:
    """Only the segments worth sending to the model."""
    return [segment for segment in segments if segment.is_speakable]
