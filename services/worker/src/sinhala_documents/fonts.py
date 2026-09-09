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

#: Individually named legacy families that carry no vendor prefix.
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

#: Legacy families this project can actually convert. Only FM-Abhaya has a
#: mapping table in ``data/legacy_fonts/``, and CLAUDE.md forbids applying it to
#: another family without validated compatibility — a wrong mapping produces
#: fluent-looking Sinhala that says something else, which is worse than none.
CONVERTIBLE_FAMILIES = frozenset({"fmabhaya"})

#: Unicode Sinhala fonts whose names begin with a legacy vendor prefix or would
#: otherwise be caught by the rules above.
_UNICODE_EXCEPTIONS = frozenset({"dlmanelunicode", "fmmalithiunicode"})

_SINHALA = re.compile(r"[\u0D80-\u0DFF]")

#: Latin letters outside ASCII. Legacy Sinhala text decodes into these heavily
#: — the accented and struck-through Latin-1 range is where the extra glyphs sit
#: — while ordinary English and romanised Sinhala barely touch them.
_NON_ASCII_LETTER = re.compile(r"[^\x00-\x7F]")

#: Fraction of characters above which text is treated as suspicious.
#:
#: **Uncalibrated.** Chosen by inspecting what the FM-Abhaya sample rows in
#: ``data/legacy_fonts/`` look like once extracted, not by measuring a labelled
#: corpus. CLAUDE.md warns against adopting a reference project's thresholds as
#: proven defaults, and this one is no better founded. It only ever escalates a
#: span to review.
SUSPICIOUS_NON_ASCII_RATIO = 0.08

#: Below this, the ratio is noise: one accented character in a six-character
#: word clears any threshold worth setting.
_MIN_LENGTH_FOR_RATIO = 12


@dataclass(frozen=True)
class LegacyFont:
    """A font identified as pre-Unicode."""

    family: str
    """Normalised family name, e.g. ``fmabhaya``."""

    raw_name: str
    convertible: bool
    """Whether a validated mapping table exists for this family."""


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
    )


def contains_sinhala(text: str) -> bool:
    return _SINHALA.search(text) is not None


def non_ascii_ratio(text: str) -> float:
    """Fraction of non-whitespace characters outside ASCII."""
    body = [character for character in text if not character.isspace()]
    if not body:
        return 0.0
    return sum(1 for character in body if _NON_ASCII_LETTER.match(character)) / len(body)


def looks_like_legacy_text(text: str) -> bool:
    """Whether ``text`` has the shape of Sinhala typed in a pre-Unicode font.

    True means "a person should look at this", not "this is legacy". Text that
    already contains Sinhala is never suspicious, and short runs are ignored
    because the ratio means nothing over a handful of characters.
    """
    stripped = text.strip()
    if len(stripped) < _MIN_LENGTH_FOR_RATIO or contains_sinhala(stripped):
        return False
    return non_ascii_ratio(stripped) >= SUSPICIOUS_NON_ASCII_RATIO
