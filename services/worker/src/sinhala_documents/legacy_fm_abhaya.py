"""Convert FM-Abhaya legacy bytes into Sinhala Unicode.

A PDF typeset in FM-Abhaya contains no Sinhala. It contains Latin characters
that a Sinhala-shaped font drew Sinhala glyphs for, and recovering the text
means undoing that substitution with the table the font was built around.

The table is vendored in ``data/legacy_fonts/fm_abhaya.tsv`` and its hash is
checked by CI. **Nothing here invents a mapping.** That matters more than usual:
a wrong entry does not crash or produce garbage — it produces fluent, plausible
Sinhala that says something the author never wrote, and no automated check
downstream can tell. So the table is used exactly as documented, and the six
supplied conversion examples are asserted character-for-character.

The documented algorithm is two ordered passes, each a longest-match-first
left-to-right scan:

1. ``[rules]`` — six entries that normalise alternate code points and reorder
   glyphs, including swaps like ``%a`` → ``a%``.
2. ``[letters]`` — 1,148 entries, longest first so that multi-character
   conjuncts beat the single letters they contain.

Left-to-right *scanning* rather than repeated global replacement is the whole
game. A scan consumes its input and never re-reads what it emitted; global
replacement would let one rule's output be rewritten by the next, and with
reordering rules in the table that silently corrupts the text.

Conversion is not the same as correctness. :func:`convert_with_report` measures
what was left unmapped and whether the result is orthographically well-formed,
because CLAUDE.md is explicit that a high proportion of Sinhala code points does
not prove a correct conversion. Those measures can find malformed output; they
cannot establish that the text says what the page says.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Bumped when the table or this algorithm changes. Part of cache identity:
#: audio generated from a previous conversion has to be invalidated, because the
#: words themselves may now be different.
CONVERTER_VERSION = "1"

#: Where the vendored table lives, relative to the repository root.
_DATA_RELATIVE = Path("data") / "legacy_fonts"

_MAPPING_FILE = "fm_abhaya.tsv"
_CASES_FILE = "fm_abhaya_cases.tsv"

#: Overrides the search when the data is mounted elsewhere — a worker container
#: does not have the repository laid out around it.
DATA_DIR_ENV = "SINHALA_LEGACY_FONT_DIR"

#: The only two section headers. A line like ``[DD<tab>ඤෲ`` is a *letter entry*
#: whose key begins with a bracket, and there are several; treating any line
#: starting with ``[`` as a header would silently drop them and leave brackets
#: scattered through the output.
_RULES_HEADER = "[rules]"
_LETTERS_HEADER = "[letters]"

_SINHALA_LETTER = re.compile(r"[අ-ෆ]")

#: Sinhala consonants. A dependent vowel sign has to attach to one of these.
_CONSONANT = re.compile(r"[ක-ෆ]")

#: Dependent vowel signs and the virama. These modify a preceding consonant and
#: are meaningless on their own — one standing alone means the conversion went
#: wrong, whatever the text looks like.
_COMBINING = re.compile(r"[්-ෟෲෳ]")

_ZWJ = "‍"

#: Latin letters left in the output. Legacy input is all Latin, so anything
#: still Latin afterwards is a code point the table had no entry for.
_UNMAPPED = re.compile(r"[A-Za-z]")


class MappingUnavailable(Exception):
    """The vendored table could not be found or parsed.

    Raised rather than falling back to an empty table. Converting with no
    mapping returns the legacy bytes unchanged, which downstream would read as
    "this text is fine" — exactly backwards.
    """


@dataclass(frozen=True)
class Mapping:
    """The two ordered passes, indexed for a longest-match-first scan."""

    rules: dict[str, str]
    letters: dict[str, str]
    source: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "_rule_index", _index(self.rules))
        object.__setattr__(self, "_letter_index", _index(self.letters))

    @property
    def rule_index(self) -> dict[str, list[str]]:
        return self._rule_index  # type: ignore[attr-defined]

    @property
    def letter_index(self) -> dict[str, list[str]]:
        return self._letter_index  # type: ignore[attr-defined]


@dataclass(frozen=True)
class ConversionReport:
    """What conversion produced, and how much of it to believe."""

    text: str
    unmapped_characters: int
    """Latin characters with no table entry. Legacy input is entirely Latin, so
    every one of these is a glyph that did not survive."""

    invalid_sequences: int
    """Combining marks still with nothing to combine with, after repair — a
    vowel sign with no consonant before it. Malformed however plausible the
    rest looks."""

    repaired_marks: int
    """Vowel signs moved back after their consonant.

    Legacy fonts store these in *visual* order, to the left of the letter they
    modify; Unicode stores them after it. The table handles the common
    spellings with combined entries, and anything it misses arrives here
    stranded. A high count means the table had gaps for this text, so it is
    reported rather than swallowed."""

    sinhala_characters: int
    total_characters: int

    @property
    def unmapped_ratio(self) -> float:
        return self.unmapped_characters / self.total_characters if self.total_characters else 0.0

    @property
    def is_well_formed(self) -> bool:
        """Whether the output is orthographically valid and fully mapped.

        Well-formed is **not** correct. It says the conversion produced legal
        Sinhala, not that it produced the right Sinhala; only a reader can say
        that. It is the strongest claim the data supports.
        """
        return self.invalid_sequences == 0 and self.unmapped_ratio <= MAX_UNMAPPED_RATIO


#: Unmapped Latin above this share of the output means the conversion did not
#: work. Kept low but not zero: legitimate Sinhala documents contain English
#: words, acronyms and numbers that pass through untouched by design.
MAX_UNMAPPED_RATIO = 0.10


def _index(table: dict[str, str]) -> dict[str, list[str]]:
    """Group keys by first character, longest first.

    The scan tries every candidate at each position, so grouping turns 1,148
    comparisons per character into a handful.
    """
    by_first: dict[str, list[str]] = {}
    for key in table:
        by_first.setdefault(key[0], []).append(key)
    for keys in by_first.values():
        keys.sort(key=len, reverse=True)
    return by_first


def data_dir() -> Path:
    """Where the vendored legacy-font tables are.

    ``SINHALA_LEGACY_FONT_DIR`` wins when set, because a deployed worker does
    not have the repository laid out around it. Otherwise the repository is
    found by walking up from this module, so nothing depends on a working
    directory or on an absolute path from another project.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _DATA_RELATIVE
        if (candidate / _MAPPING_FILE).is_file():
            return candidate
    raise MappingUnavailable(
        f"Could not find {_DATA_RELATIVE / _MAPPING_FILE} above {__file__}. "
        f"Set {DATA_DIR_ENV} to the directory holding the vendored legacy font tables."
    )


def _parse(text: str, source: Path) -> tuple[dict[str, str], dict[str, str]]:
    rules: dict[str, str] = {}
    letters: dict[str, str] = {}
    section: dict[str, str] | None = None

    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if line == _RULES_HEADER:
            section = rules
            continue
        if line == _LETTERS_HEADER:
            section = letters
            continue
        if section is None or "\t" not in line:
            continue
        key, _, value = line.partition("\t")
        if key:
            section[key] = value

    if not letters:
        raise MappingUnavailable(f"{source} contains no [letters] entries.")
    return rules, letters


@lru_cache(maxsize=1)
def load_mapping() -> Mapping:
    """Read and index the vendored table. Cached; the file never changes."""
    directory = data_dir()
    path = directory / _MAPPING_FILE
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MappingUnavailable(f"Could not read {path}: {error}") from error
    rules, letters = _parse(content, path)
    return Mapping(rules=rules, letters=letters, source=path)


def load_cases() -> list[tuple[str, str]]:
    """The supplied legacy/Unicode example pairs, for verification."""
    path = data_dir() / _CASES_FILE
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MappingUnavailable(f"Could not read {path}: {error}") from error
    cases = []
    for line in content.splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        legacy, _, expected = line.partition("\t")
        cases.append((legacy, expected))
    return cases


def _scan(text: str, table: dict[str, str], by_first: dict[str, list[str]]) -> str:
    """One longest-match-first, left-to-right pass.

    Output is appended and never re-examined. That is what makes the reordering
    rules safe: ``%a`` → ``a%`` must not have its own output rewritten by the
    rule for ``a%``.
    """
    out: list[str] = []
    position = 0
    end = len(text)
    while position < end:
        for key in by_first.get(text[position], ()):
            if text.startswith(key, position):
                out.append(table[key])
                position += len(key)
                break
        else:
            out.append(text[position])
            position += 1
    return "".join(out)


def _is_anchor(character: str) -> bool:
    """Whether a combining mark may legitimately attach to ``character``."""
    return bool(
        character
        and (_CONSONANT.match(character) or _COMBINING.match(character) or character == _ZWJ)
    )


def repair_stranded_marks(text: str) -> tuple[str, int]:
    """Move vowel signs back after the consonant they belong to.

    Legacy fonts store a vowel sign where it is *drawn* — for several Sinhala
    signs, to the left of the letter it modifies. Unicode stores it after.
    The table resolves this with combined entries (``fod`` → ``දො``), but only
    for the spellings it lists: the same word set with the variant code point
    ``Þ`` has no ``fÞ`` entry, so ``ෙ`` and ``දා`` are converted separately and
    the sign is left stranded in front.

    The repair is deliberately narrow. It only moves a mark that is **already
    malformed** — one with no consonant, mark or ZWJ before it — and only when
    a consonant follows for it to attach to. Well-formed output contains no such
    marks, so correctly converted text cannot be disturbed: in ``දෙර`` the sign
    already follows ``ද`` and is left alone, even though a consonant follows it
    too.

    Composing afterwards is standard Unicode, not a decision made here: ``ො`` is
    canonically ``ෙ`` followed by ``ා``, so NFC joins them once the order is
    right.

    This goes beyond the table's documented two passes, so it is reported —
    see :attr:`ConversionReport.repaired_marks` — and **wants a native
    speaker's confirmation** on real pages, like the number words do.
    """
    out: list[str] = []
    repaired = 0
    position = 0
    while position < len(text):
        character = text[position]
        if _COMBINING.match(character) and not _is_anchor(out[-1] if out else ""):
            following = text[position + 1] if position + 1 < len(text) else ""
            if _CONSONANT.match(following):
                out.append(following)
                out.append(character)
                repaired += 1
                position += 2
                continue
        out.append(character)
        position += 1
    return unicodedata.normalize("NFC", "".join(out)), repaired


def convert(text: str) -> str:
    """Convert FM-Abhaya legacy text to Sinhala Unicode.

    Only ever call this on text known to be in FM-Abhaya. Applied to anything
    else — another legacy family, or ordinary English — it produces confident
    Sinhala-looking output that means nothing, which is the failure this whole
    package exists to prevent.

    Note what that implies: the checks in :func:`convert_with_report` measure
    whether output is *well formed*, and cannot be used to decide whether the
    input was FM-Abhaya in the first place. Ordinary English put through this
    table sometimes converts to orthographically legal Sinhala. The font name is
    the gate; these measures only describe how the conversion went.
    """
    mapping = load_mapping()
    after_rules = _scan(text, mapping.rules, mapping.rule_index)
    letters = _scan(after_rules, mapping.letters, mapping.letter_index)
    return repair_stranded_marks(letters)[0]


def count_invalid_sequences(text: str) -> int:
    """Combining marks with no consonant to attach to.

    A dependent vowel sign or virama modifies the consonant before it. One that
    begins a word, or follows a space or a vowel sign that itself follows
    nothing, is malformed — the conversion dropped or misordered a glyph. This
    finds broken output; it cannot find output that is well-formed and wrong.
    """
    invalid = 0
    for position, character in enumerate(text):
        if not _COMBINING.match(character):
            continue
        previous = text[position - 1] if position else ""
        if not previous:
            invalid += 1
            continue
        # A consonant, another mark in the same cluster, or the ZWJ that joins a
        # conjunct are all legitimate anchors.
        if not (_CONSONANT.match(previous) or _COMBINING.match(previous) or previous == _ZWJ):
            invalid += 1
    return invalid


def convert_with_report(text: str) -> ConversionReport:
    """Convert, and measure how much of the result to trust."""
    mapping = load_mapping()
    after_rules = _scan(text, mapping.rules, mapping.rule_index)
    letters = _scan(after_rules, mapping.letters, mapping.letter_index)
    converted, repaired = repair_stranded_marks(letters)
    stripped = "".join(converted.split())
    return ConversionReport(
        text=converted,
        unmapped_characters=len(_UNMAPPED.findall(converted)),
        invalid_sequences=count_invalid_sequences(converted),
        repaired_marks=repaired,
        sinhala_characters=len(_SINHALA_LETTER.findall(converted)),
        total_characters=len(stripped),
    )
