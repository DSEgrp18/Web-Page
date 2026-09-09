"""Turn display text into text the vendored front end can safely narrate.

This module wraps the vendored front end. It never modifies it. The front end's
behaviour is what the model heard during training, so changing it would silently
alter pronunciation and invalidate the fine-tune; but it is also lossy, so
anything that needs preserving has to be handled *before* it runs, while the
information still exists.

Two defects recorded in ``tests/test_text_frontend_characterisation.py`` are
fixed here:

* **Digits are deleted.** Numbers are written out as Sinhala words first.
* **Newlines and tabs are deleted rather than collapsed**, joining the words on
  either side. Whitespace is normalised to single spaces first. This one matters
  on nearly every line of a real PDF.

A third is deliberately *not* fixed here, because it is a quality judgement
rather than data loss: English-only text is romanised as though it were Sinhala,
so ``"computer"`` becomes ``"chomputher"``. See :func:`to_model_input`.

Three stages, kept separate on purpose
--------------------------------------
CLAUDE.md requires the original extraction, the corrected display text, and the
spoken text to be stored separately, and requires that speech-expanded text is
never the only source for display or retrieval. So:

``display text`` → :func:`to_speech_text` → ``spoken text`` (still Sinhala
script, readable, storable) → :func:`to_model_input` → ``model text`` (ASCII,
only meaningful to the model).

The middle stage is the one worth keeping. It is what a reviewer can check, what
a listener could be shown, and what makes a pronunciation complaint diagnosable.
"""

from __future__ import annotations

import re

from .sinhala_numbers import (
    DECIMAL_POINT,
    PERCENT,
    NumberOutOfRangeError,
    cardinal,
    digits_individually,
)
from .vendor.sinhala_text import to_ascii

# Bump when any behaviour in this module changes the text it produces. Cached
# audio identity includes this, so a change here must invalidate that audio:
# CLAUDE.md requires the normalizer version in the cache key alongside the text
# hash, document version, model version, voice, and generation settings.
NORMALIZER_VERSION = "1"

# Characters that carry no sound and must be removed rather than turned into a
# space, or they would split a word in two.
_ZERO_WIDTH = dict.fromkeys(
    map(
        ord,
        (
            "​"  # zero width space
            "‌"  # zero width non-joiner
            "﻿"  # byte order mark
            "­"  # soft hyphen, inserted by PDF layout at line breaks
        ),
    )
)

# Deliberately excludes U+200D ZERO WIDTH JOINER: it is meaningful in Sinhala
# conjuncts, and the vendored front end removes it itself at the right moment.

_WHITESPACE = re.compile(r"\s+")

# A number with optional thousands separators and an optional decimal part, and
# an optional trailing percent sign. Matched as a whole so "1,500.50" is one
# token rather than three.
#
# The percent group keeps its own optional whitespace *inside* the optional
# group. Writing it as `\s*(%?)` instead would consume the space after every
# ordinary number and glue the expansion to the following word — reintroducing,
# through the fix, the very defect this module exists to remove.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:\s*(%))?")


def normalize_whitespace(text: str) -> str:
    """Collapse every run of whitespace to one space, and strip.

    The front end filters characters against an allowed set that contains a
    space but not ``\\n`` or ``\\t``, and it collapses whitespace only *after*
    that filtering. Line breaks are therefore deleted, not turned into spaces,
    and the words on either side are joined: ``"line one\\nline two"`` narrates
    as ``"line oneline thwo"``. Extracted PDF text is full of line breaks, so
    this has to be handled before the front end sees the text.
    """
    text = text.translate(_ZERO_WIDTH)
    return _WHITESPACE.sub(" ", text).strip()


def _expand_match(match: re.Match[str]) -> str:
    integer_part = match.group(1).replace(",", "")
    fraction_part = match.group(2)
    percent = match.group(3)

    try:
        words = cardinal(int(integer_part))
    except NumberOutOfRangeError:
        # Too large to write out with confidence. Read it digit by digit rather
        # than dropping it or inventing a form. Clumsy, but nothing is lost and
        # nothing is fabricated.
        words = digits_individually(integer_part)

    if fraction_part is not None:
        words = f"{words} {DECIMAL_POINT} {digits_individually(fraction_part)}"

    if percent:
        # Sinhala puts the marker first: 50% is "සියයට පනහ", not "පනහ සියයට".
        words = f"{PERCENT} {words}"

    return words


def expand_numbers(text: str) -> str:
    """Write digits out as Sinhala words.

    Handles integers, thousands separators, decimals, and a trailing percent
    sign. Ordinals, currency, dates, and times are not handled yet and will be
    read as plain numbers.
    """
    return _NUMBER.sub(_expand_match, text)


def to_speech_text(text: str, *, numbers_as_words: bool = True) -> str:
    """Display text to spoken text: still Sinhala, but safe to narrate.

    The result is human-readable Sinhala. Store it alongside the display text
    rather than instead of it — display and retrieval must keep the original,
    because "42" is what a reader searches for, not "හතළිස් දෙක".
    """
    text = normalize_whitespace(text)
    if numbers_as_words:
        text = expand_numbers(text)
    # Expansion inserts spaces, and may have introduced doubles around a number
    # that was already surrounded by them.
    return _WHITESPACE.sub(" ", text).strip()


def to_model_input(text: str, *, numbers_as_words: bool = True) -> str:
    """Spoken text to the ASCII the model is actually given.

    This is the only place the vendored front end is called. The output is not
    meaningful to a human and must never be stored as the document's text or
    indexed for retrieval; it exists solely to be tokenised.

    Note on English: a segment containing no Sinhala at all is romanised as
    though it were Sinhala, so ``"computer"`` becomes ``"chomputher"``. That is
    not corrected here. Routing such text differently would change pronunciation
    on the basis of reasoning alone, and pronunciation changes need a listening
    comparison before they are adopted. It is recorded in the manifest as an
    open question.
    """
    return to_ascii(to_speech_text(text, numbers_as_words=numbers_as_words))


def is_speakable(model_text: str) -> bool:
    """Whether there is anything left to synthesise.

    Text can normalise to nothing at all — a segment of only symbols, or only
    digits when expansion is disabled. Asking the model to synthesise an empty
    string produces a silent clip that a cache would happily store as valid
    audio, and a listener would experience as the reader skipping a sentence
    with no explanation. Callers must check this before synthesising.
    """
    return any(character.isalnum() for character in model_text)


def contains_sinhala(text: str) -> bool:
    """Whether the text has any character in the Sinhala block (U+0D80-U+0DFF).

    The front end dispatches on exactly this, so it decides whether a segment
    is romanised as Sinhala or mangled as pseudo-Sinhala English. Exposed for
    segment-level language handling later.
    """
    return any("඀" <= character <= "෿" for character in text)
