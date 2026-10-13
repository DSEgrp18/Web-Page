"""Word-level pronunciation overrides. Experimental, opt-in, and inference only.

The trained model reads ASCII made by the bundled ``sinhala_text.py``, and that
converter writes ඟ as ``ng``: a nasal with no ``g`` after it, which the
tokenizer then reads as the English token ``gang``. ඹ, ඳ and ඬ keep their
stop (``mb``, ``ndh``, ``nd``); ඟ alone loses it. Whether another spelling
sounds better is a question for native listeners, not for this code.

So this is a *dictionary*, not a rule:

- **Whole words only.** An entry replaces a Sinhala word exactly as written,
  after NFC normalisation. Nothing matches inside a longer word, and no letter
  is rewritten everywhere it occurs.
- **Off unless asked for.** ``SINHALA_TTS_PRONUNCIATION_OVERRIDES`` names a
  TSV file. Unset, every output is byte-for-byte what it was.
- **At synthesis, never in storage.** Applied when audio is made
  (``TtsAdapter.prepare_text``), so a book's stored text and its model text
  are untouched and switching the file off restores the original speech.
- **Its own variant.** The file's digest is added to the normaliser version
  recorded with every clip and to the cache key, so override audio is never
  served as the original, nor the original as override audio.
- **The converter and the model are not changed.** Words without an entry go
  through ``sinhala_text.py`` exactly as before.

The file, one entry per line, ``#`` for comments::

    # word<TAB>ascii<TAB>why (optional)
    ගඟ	gangga	blind test 2026-10, 7 of 9 listeners

Spellings are checked to be lowercase ASCII letters with ``'`` or ``-``
between them. That is a format check, not a pronunciation check: a spelling
the tokenizer accepts can still sound wrong.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .normalize import NORMALIZER_VERSION
from .vendor.sinhala_text import sinhala_to_ascii, to_ascii

ENV = "SINHALA_TTS_PRONUNCIATION_OVERRIDES"

#: A Sinhala word: a run of Sinhala letters and signs, with the joiners that
#: are part of Sinhala words. Punctuation and spaces end it.
_SINHALA_WORD = re.compile("[඀-෿‌‍]+")
_SPELLING = re.compile(r"[a-z]+(?:['-][a-z]+)*")


class OverrideFileError(ValueError):
    """The override file is malformed. Raised at load, never half-applied."""


@dataclass(frozen=True)
class Overrides:
    """Sinhala word to the ASCII the model is given for it."""

    words: dict[str, str]
    #: Digest of the entries. Changes whenever any entry does.
    version: str

    def substitute(self, spoken: str) -> tuple[str, int]:
        """The text with each listed word replaced, and how many were."""
        hits = 0

        def swap(match: re.Match[str]) -> str:
            nonlocal hits
            spelling = self.words.get(match.group(0))
            if spelling is None:
                return match.group(0)
            hits += 1
            return spelling

        return _SINHALA_WORD.sub(swap, unicodedata.normalize("NFC", spoken)), hits

    def model_input(self, spoken: str) -> str:
        """``to_ascii(spoken)``, with listed words spelled as listed.

        With no listed word present this *is* ``to_ascii(spoken)``. Otherwise
        the replaced spellings are already ASCII, which the script converter
        passes through, and every other word is converted exactly as before.
        """
        replaced, hits = self.substitute(spoken)
        if hits == 0:
            return to_ascii(spoken)
        return sinhala_to_ascii(replaced)


def parse(text: str) -> Overrides:
    """Read the TSV format above. Raises :class:`OverrideFileError`."""
    words: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in raw.split("\t")]
        if len(fields) < 2:
            raise OverrideFileError(f"line {number}: expected word<TAB>ascii")
        word = unicodedata.normalize("NFC", fields[0])
        spelling = fields[1]
        if not _SINHALA_WORD.fullmatch(word):
            raise OverrideFileError(f"line {number}: {word!r} is not a single Sinhala word")
        if not _SPELLING.fullmatch(spelling):
            raise OverrideFileError(
                f"line {number}: {spelling!r} must be lowercase ASCII letters, "
                "with ' or - only between them"
            )
        if word in words and words[word] != spelling:
            raise OverrideFileError(f"line {number}: {word} is listed twice, differently")
        words[word] = spelling
    canonical = "\n".join(f"{w}\t{s}" for w, s in sorted(words.items()))
    version = "ovr-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return Overrides(words=words, version=version)


def load(path: str | Path) -> Overrides:
    return parse(Path(path).read_text(encoding="utf-8-sig"))


_cache: dict[tuple[str, int, int], Overrides] = {}
_lock = threading.Lock()


def active() -> Overrides | None:
    """The overrides named by :data:`ENV`, or ``None`` when it is unset.

    Re-read when the file changes. A named file that is missing or malformed
    raises: an operator who asked for overrides must not silently get none.
    """
    setting = os.environ.get(ENV, "").strip()
    if not setting:
        return None
    path = Path(setting)
    try:
        stat = path.stat()
    except OSError as error:
        raise OverrideFileError(f"{ENV}={setting!r} cannot be read: {error}") from error
    key = (str(path.resolve()), stat.st_size, int(stat.st_mtime_ns))
    with _lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = load(path)
        return _cache[key]


def normalizer_version() -> str:
    """What every clip records as its normaliser: the base, plus any overrides."""
    found = active()
    return NORMALIZER_VERSION if found is None else f"{NORMALIZER_VERSION}+{found.version}"
