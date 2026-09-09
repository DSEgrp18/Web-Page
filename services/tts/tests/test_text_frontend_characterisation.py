"""What the vendored front end actually does, measured rather than assumed.

These are characterisation tests: they record real current behaviour, including
behaviour that is wrong for a document reader. They are not a statement that the
behaviour is correct. Their job is to make any change to it visible, and to stop
the defects below from being rediscovered from scratch every few months.

Three of the behaviours recorded here are defects for our use case, and each is
marked `DEFECT`. They are fixed by *wrapping* the front end with a normaliser
that runs before it, never by editing it — editing it would change what the
model hears and invalidate the fine-tune. When that normaliser lands, the
`DEFECT` tests below should be updated to assert the corrected pipeline while
these keep asserting the raw front end's unchanged behaviour.

CLAUDE.md, "Model-specific checks from the reference project", requires exactly
this: test years, prices, decimals, page references, and mixed-language input
through the real path rather than trusting notes from another project.
"""

from __future__ import annotations

import pytest

from sinhala_tts.vendor.sinhala_text import _KEEP, fold, sinhala_to_ascii, to_ascii

# --------------------------------------------------------------------------
# Core romanisation: the behaviour the fine-tune depends on
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sinhala", "expected"),
    [
        ("ආයුබෝවන්", "aayuboovan"),
        ("මම ගෙදර යනවා.", "mama gedhara yanavaa."),
        # Retroflex ට -> t and dental ත -> th, the distinction the mapping exists for.
        ("පිටුව", "pituva"),
        # ZWJ conjunct: the joiner carries no sound and is dropped.
        ("ක්‍ෂ", "ksha"),
    ],
)
def test_sinhala_script_romanises(sinhala: str, expected: str) -> None:
    assert to_ascii(sinhala) == expected


def test_output_is_always_ascii() -> None:
    """Any non-ASCII byte reaching the tokenizer becomes [UNK] and ruins the word."""
    samples = [
        "ආයුබෝවන් 2024",
        "මෙය PDF ලේඛනයකි",
        "ක්‍ෂ ඥ ඤ ඹ ඳ",
        "The cat sat on the mat.",
    ]
    for sample in samples:
        out = to_ascii(sample)
        assert out.isascii(), f"non-ASCII leaked through for {sample!r}: {out!r}"
        assert set(out) <= _KEEP, f"characters outside _KEEP in {out!r}"


def test_to_ascii_dispatches_on_presence_of_sinhala() -> None:
    """Any Sinhala codepoint routes the whole string through the script path.

    This is why English inside a Sinhala sentence survives but a pure English
    sentence does not: they take different branches.
    """
    assert to_ascii("මෙය PDF ලේඛනයකි") == sinhala_to_ascii("මෙය PDF ලේඛනයකි")
    assert to_ascii("computer") == fold("computer")


# --------------------------------------------------------------------------
# DEFECT 1: digits are silently deleted
# --------------------------------------------------------------------------
# `_normalise` keeps only characters in `_KEEP`, which contains no digits, so
# every number vanishes without warning. For a document reader this is serious:
# page references, years, prices, section numbers, and list numbering are all
# lost, and the listener is given a fluent sentence with the number missing
# rather than any indication that something was dropped.
#
# The fix is number expansion into Sinhala words BEFORE this front end runs,
# because the front end is lossy and cannot be undone afterwards. CLAUDE.md:
# "Any required number expansion happens before a lossy romanizer and only in
# spoken text."


@pytest.mark.parametrize(
    ("text", "expected", "what_is_lost"),
    [
        ("2024 වර්ෂය", "varshaya", "the year"),
        ("පිටුව 42 බලන්න", "pituva balanna", "the page number"),
        ("3.14", ".", "the whole number, leaving a bare full stop"),
        ("රු. 1500.50", "ru. .", "the price"),
        ("1 2 3 4 5 6 7 8 9 0", "", "every digit"),
        ("12345", "", "everything, producing empty text"),
        ("50% සහ $100", "saha", "both numbers and both symbols"),
    ],
)
def test_defect_digits_are_silently_dropped(text: str, expected: str, what_is_lost: str) -> None:
    assert to_ascii(text) == expected, what_is_lost


def test_defect_numeric_only_text_synthesises_to_nothing() -> None:
    """A segment that is only digits produces empty text.

    Passed to the model this would request synthesis of an empty string. The
    adapter must reject empty output rather than generating a silent clip and
    caching it as valid audio.
    """
    assert to_ascii("42") == ""


# --------------------------------------------------------------------------
# DEFECT 2: newlines and tabs are deleted, gluing words together
# --------------------------------------------------------------------------
# `_KEEP` contains a space but not `\n` or `\t`, and the whitespace-collapsing
# regex runs only after those characters have already been filtered out. Line
# breaks therefore do not become spaces; they disappear, and the words on either
# side are joined into one.
#
# This matters more than it looks: text extracted from a PDF is full of line
# breaks, so this would corrupt a word on nearly every line of a real document.
# The wrapper must collapse whitespace to single spaces before calling in.


def test_defect_newline_joins_words() -> None:
    # Both defects at once, which is what a real English caption in a PDF hits:
    # the newline glues "one" to "line", and "two" is romanised to "thwo".
    assert to_ascii("line one\nline two") == "line oneline thwo"


def test_defect_tab_joins_words() -> None:
    assert to_ascii("column\tvalue") == "cholumnvalue"


def test_defect_newline_in_sinhala_joins_words() -> None:
    """The same fault on the script path, which is where real documents hit it."""
    assert to_ascii("මම\nගෙදර") == "mamagedhara"


# --------------------------------------------------------------------------
# DEFECT 3: English-only text is romanised as if it were Sinhala
# --------------------------------------------------------------------------
# With no Sinhala codepoint present, `to_ascii` takes the `fold` branch, which
# applies the romanisation mapping to plain English: t -> th, d -> dh, c -> ch.
# "computer" becomes "chomputher".
#
# For an English word inside a Sinhala sentence this does not happen, because
# the script branch passes unknown characters through untouched. So the fault
# only appears for segments that are entirely English — which a Sinhala textbook
# certainly contains: English headings, captions, references, and code.


@pytest.mark.parametrize(
    ("english", "mangled"),
    [
        ("computer", "chomputher"),
        ("The cat sat on the mat.", "the chath sath on the math."),
        ("PDF OCR API", "pdhf ochr api"),
    ],
)
def test_defect_english_only_text_is_mangled(english: str, mangled: str) -> None:
    assert to_ascii(english) == mangled


def test_english_inside_sinhala_survives_intact() -> None:
    """The contrast that makes the defect above easy to miss."""
    assert to_ascii("මෙය PDF ලේඛනයකි") == "meya pdf leekanayaki"


# --------------------------------------------------------------------------
# Punctuation: what actually survives
# --------------------------------------------------------------------------
# The module docstring claims the output charset includes "(", ")" and "=".
# It does not; `_KEEP` excludes them. Recorded here because the docstring is
# the first thing a reader trusts, and it is wrong.


def test_parentheses_and_equals_are_stripped_despite_docstring() -> None:
    assert to_ascii("test (one) = two") == "thesth one thwo"


def test_symbols_alone_produce_empty_text() -> None:
    assert to_ascii("()[]{}#@") == ""


def test_sentence_punctuation_survives() -> None:
    assert to_ascii("මම ගෙදර යනවා. ඔබ කොහෙද?") == "mama gedhara yanavaa. oba kohedha?"


def test_empty_input_gives_empty_output() -> None:
    assert to_ascii("") == ""
