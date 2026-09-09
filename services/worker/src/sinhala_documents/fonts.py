"""Recognise pre-Unicode Sinhala fonts from PDF font metadata.

Before Unicode was usable on Sri Lankan desktops, Sinhala was typed in fonts
that put Sinhala glyphs at Latin code points. A PDF made that way carries no
Sinhala at all: the text extractor faithfully returns the Latin characters the
file actually contains, and they are meaningless. Nothing about that output is
malformed, so nothing downstream notices — the reader simply narrates rubbish
in a confident voice. That is the failure this module exists to prevent.

Two independent signals, deliberately kept apart:

* **The font name.** Authoritative when it matches a known family, and the
  signal CLAUDE.md asks for. Subset prefixes have to be normalised away first:
  a PDF that embeds only the glyphs it used renames the font ``ABCDEF+FMAbhaya``.
* **The shape of the text.** A fallback for fonts nobody has catalogued. It is a
  heuristic, it is **not calibrated against ground truth**, and it can only
  raise suspicion — never clear it, and never on its own justify withholding a
  page. CLAUDE.md is explicit that orthography checks cannot establish
  correctness, so this one is used to ask for review, nothing more.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Six uppercase letters and a plus sign, prepended by PDF producers to the name
#: of an embedded subset. ``ABCDEF+FMAbhaya`` and ``FMAbhaya`` are one font.
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")

#: Weight, style, and foundry words that appear glued to a family name. Stripped
#: repeatedly and longest-first, because they stack: "TimesNewRomanPSMT" carries
#: both a PostScript and a Monotype suffix. Removed only when something is left
#: over, so a font genuinely called "Bold" survives.
#:
#: "Roman" is deliberately absent even though it is a real PostScript style:
#: stripping it turns Times New Roman into "timesnew", and no legacy family
#: name ends in it, so the collision costs more than the suffix is worth.
_STYLE_SUFFIXES = (
    "boldital",
    "bolditalic",
    "boldoblique",
    "semibold",
    "extrabold",
    "italic",
    "oblique",
    "regular",
    "normal",
    "plain",
    "light",
    "medium",
    "black",
    "bold",
    "ital",
    "mt",
    "ps",
)

#: Vendor prefixes whose Sinhala families are pre-Unicode as a rule. FontMaster
#: ("FM ...") and DL are the two that dominate older Sri Lankan documents.
_LEGACY_PREFIXES = ("fm", "dl")

#: Individually named legacy Sinhala families that carry no vendor prefix.
#:
#: Only Sinhala. Sri Lankan textbooks are trilingual and the first real book
#: this was run against sets Tamil in legacy fonts too, but this reader does
#: not serve Tamil and cataloguing its fonts would be scope it cannot honour.
#: Such text is withheld by :func:`is_unreadable_script` instead, which needs
#: no list and no language to be named.
_LEGACY_NAMES = frozenset(
    {
        "kaputa",
        "kaputaunicode",
        "thibus",
        "sinhalathibus",
        "araliya",
        "ariyalu",
        "wije",
        "sinhalaweb",
    }
)

#: Families whose names suggest a variant of a family we *can* convert, without
#: proving it. ``FMAbabld`` is almost certainly FM-Abhaya Bold — it sets the
#: headings in a book whose body is FM-Abhaya — but "almost certainly" is not
#: the standard CLAUDE.md sets for applying a mapping table, because a wrong
#: table produces fluent Sinhala saying something the author never wrote.
#:
#: So this changes the note, not the verdict. Whoever implements the converter
#: gets told where to look; nothing is decoded on a guess.
_VARIANT_OF = {
    "fmababld": "fmabhaya",
    "fmabhayabld": "fmabhaya",
}

#: Legacy families this project can actually convert. Only FM-Abhaya has a
#: mapping table in ``data/legacy_fonts/``, and CLAUDE.md forbids applying it to
#: another family without validated compatibility — a wrong mapping produces
#: fluent-looking Sinhala that says something else, which is worse than none.
CONVERTIBLE_FAMILIES = frozenset({"fmabhaya"})

#: Unicode Sinhala fonts whose names begin with a legacy vendor prefix or would
#: otherwise be caught by the rules above.
_UNICODE_EXCEPTIONS = frozenset({"dlmanelunicode", "fmmalithiunicode"})

_SINHALA = re.compile(r"[\u0D80-\u0DFF]")

#: Characters outside ASCII. A font for a non-Latin script that lacks a usable
#: Unicode mapping decodes almost entirely into these.
_NON_ASCII_LETTER = re.compile(r"[^\x00-\x7F]")

#: A capital letter *inside* a word. This is the signal that actually works.
#:
#: Legacy Sinhala fonts assign glyphs to Latin code points without regard to
#: case, so decoded text is littered with interior capitals: ``wOHdmk``,
#: ``m%ldYk``, ``fomd¾;fïka;=j``. English words do not do this outside acronyms
#: and CamelCase.
_INTERIOR_CAPITAL = re.compile(r"\w[A-Z]")

#: Interior-capital rate above which text is not readable prose in any language
#: this project serves.
#:
#: **Measured, on one real book** — a 168-page Grade 11 Sinhala history
#: textbook, aggregated per font:
#:
#: =========================== ======== =========
#: font                        interior non-ASCII
#: =========================== ======== =========
#: FM-Abhaya (legacy)             0.202     0.073
#: FM-Abhaya Bold (legacy)        0.221     0.068
#: CIDFont+F2 (legacy, unnamed)   0.191     0.056
#: Times New Roman (English)      0.083     0.016
#: English control sentences      0.033     0.000
#: =========================== ======== =========
#:
#: One book is not a corpus, and CLAUDE.md is explicit that thresholds must be
#: calibrated against ground truth rather than adopted as proven defaults. The
#: gap between the two clusters is wide, so this sits between them; it should be
#: re-measured as more real documents arrive.
#:
#: Note what the table also shows: FM-Abhaya's non-ASCII rate is 0.073, so a
#: non-ASCII threshold alone would have missed the entire book.
SUSPICIOUS_INTERIOR_CAPITAL_RATIO = 0.15

#: Non-ASCII rate above which a *span* is suspicious.
SUSPICIOUS_NON_ASCII_RATIO = 0.08

#: Non-ASCII rate above which text is not in a script this reader can speak.
#:
#: This is a Sinhala reader with a Sinhala voice. Text that carries no Sinhala
#: and is overwhelmingly outside ASCII is written in some other script — and
#: which one does not matter, because the answer is the same either way: it
#: cannot be narrated, so it is withheld rather than spoken.
#:
#: Naming languages here would be the wrong shape. Sri Lankan textbooks are
#: trilingual and the first real book this ran against sets Tamil in a legacy
#: font, but keeping a catalogue of Tamil fonts would promise support this
#: reader does not offer. One ratio covers every script at once.
#:
#: Measured on that book: the legacy Tamil font scored 0.78 and decorative
#: dingbats 1.00, while legacy Sinhala sat at 0.07 and English at 0.02. The
#: threshold has a wide margin on both sides.
FOREIGN_SCRIPT_NON_ASCII_RATIO = 0.5

#: Below this, the non-ASCII ratio is noise: one accented character in a
#: six-character word clears any threshold worth setting.
_MIN_LENGTH_FOR_RATIO = 12

#: The interior-capital rate is a per-word statistic and needs several words
#: before it means anything. A single acronym in a short line reads as 1.00.
_MIN_LENGTH_FOR_CAPITALS = 40

#: Text per font per page before the font itself is judged. Aggregating is what
#: makes this reliable: "NASA and the UNESCO report" scores 0.167 on its own but
#: 0.033 inside a paragraph, and it is the paragraph that describes the font.
MIN_LENGTH_FOR_FONT_VERDICT = 200


@dataclass(frozen=True)
class LegacyFont:
    """A font identified as pre-Unicode."""

    family: str
    """Normalised family name, e.g. ``fmabhaya``."""

    raw_name: str
    convertible: bool
    """Whether a validated mapping table exists for this family."""

    variant_of: str | None = None
    """A family this one may be a styled variant of, unproven.

    Set where the name is suggestive and the verdict is not: it changes what
    a reviewer is told, never what gets decoded.
    """


def normalise_font_name(raw_name: str) -> str:
    """Reduce a PDF font name to a comparable family name.

    Strips the subset prefix, the PostScript style suffix, punctuation, and
    case, so ``ABCDEF+FM-Abhaya-Bold`` and ``FMAbhaya`` both become
    ``fmabhaya``.
    """
    name = _SUBSET_PREFIX.sub("", raw_name or "")
    # A PostScript name separates the style with a comma or a hyphen.
    name = re.split(r"[,]", name, maxsplit=1)[0]
    name = re.sub(r"[^A-Za-z0-9]", "", name).lower()

    while True:
        for suffix in sorted(_STYLE_SUFFIXES, key=len, reverse=True):
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                break
        else:
            return name


def identify_legacy_font(raw_name: str) -> LegacyFont | None:
    """Identify ``raw_name`` as a legacy Sinhala font, or return ``None``.

    Recognition is by name only. A font this does not know is not thereby
    proven to be Unicode — see :func:`looks_like_legacy_text` for the weaker
    second signal.
    """
    family = normalise_font_name(raw_name)
    if not family or family in _UNICODE_EXCEPTIONS:
        return None
    if family.endswith("unicode"):
        return None

    matched = family in _LEGACY_NAMES or any(
        family.startswith(prefix) and len(family) > len(prefix) for prefix in _LEGACY_PREFIXES
    )
    if not matched:
        return None
    return LegacyFont(
        family=family,
        raw_name=raw_name,
        convertible=family in CONVERTIBLE_FAMILIES,
        variant_of=_VARIANT_OF.get(family),
    )


def contains_sinhala(text: str) -> bool:
    return _SINHALA.search(text) is not None


def non_ascii_ratio(text: str) -> float:
    """Fraction of non-whitespace characters outside ASCII."""
    body = [character for character in text if not character.isspace()]
    if not body:
        return 0.0
    return sum(1 for character in body if _NON_ASCII_LETTER.match(character)) / len(body)


def interior_capital_ratio(text: str) -> float:
    """Fraction of multi-letter words carrying a capital somewhere inside them."""
    words = [word for word in text.split() if len(word) > 1]
    if not words:
        return 0.0
    return sum(1 for word in words if _INTERIOR_CAPITAL.search(word)) / len(words)


def looks_like_legacy_text(text: str) -> bool:
    """Whether one run of text has the shape of a broken encoding.

    A backstop for short runs in fonts nobody has catalogued. True means "a
    person should look at this", not "this is legacy". Text that already
    contains Sinhala is never suspicious.
    """
    stripped = text.strip()
    if contains_sinhala(stripped):
        return False
    if (
        len(stripped) >= _MIN_LENGTH_FOR_RATIO
        and non_ascii_ratio(stripped) >= SUSPICIOUS_NON_ASCII_RATIO
    ):
        return True
    return (
        len(stripped) >= _MIN_LENGTH_FOR_CAPITALS
        and interior_capital_ratio(stripped) >= SUSPICIOUS_INTERIOR_CAPITAL_RATIO
    )


def is_unreadable_script(text: str) -> bool:
    """Whether ``text`` is in a script this reader has no voice for.

    Withholding, not flagging. A Sinhala voice given Tamil, Devanagari or
    dingbats produces confident noise, and the listener — who cannot see the
    page — has no way to tell that is what happened.

    Deliberately says nothing about *which* script. The reader serves Sinhala;
    everything else is equally unspeakable, and a language list would imply a
    support commitment that does not exist.
    """
    stripped = text.strip()
    if len(stripped) < _MIN_LENGTH_FOR_RATIO or contains_sinhala(stripped):
        return False
    return non_ascii_ratio(stripped) >= FOREIGN_SCRIPT_NON_ASCII_RATIO


def font_encoding_looks_wrong(aggregated_text: str) -> bool:
    """Whether all the text set in one font, on one page, decodes to nonsense.

    This is the check that matters, and it is deliberately made about the *font*
    rather than about a line. Encoding is a property of the font: it is the same
    for every character set in it, so the evidence is every character set in it.
    Judging line by line throws that away and asks a question about twenty
    characters that only a paragraph can answer.

    The real book that prompted this had 3,293 characters in a font named only
    ``KQAHVM+CIDFont+F2`` — nothing in the name to identify, no Sinhala in the
    output, and a per-line non-ASCII rate below any usable threshold. Aggregated,
    it is unmistakable.
    """
    stripped = aggregated_text.strip()
    if len(stripped) < MIN_LENGTH_FOR_FONT_VERDICT or contains_sinhala(stripped):
        return False
    return (
        interior_capital_ratio(stripped) >= SUSPICIOUS_INTERIOR_CAPITAL_RATIO
        or non_ascii_ratio(stripped) >= SUSPICIOUS_NON_ASCII_RATIO
    )
