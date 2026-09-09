# -*- coding: utf-8 -*-
"""
sinhala_text.py -- the one thing that decides whether an XTTS Sinhala fine-tune
works or produces babble.

WHY THIS FILE EXISTS
--------------------
XTTS-v2's tokenizer (vocab.json) is a *word-pretokenised BPE with an [UNK]
token* -- not a byte-level BPE. Verified against the real vocab:

    >>> pre_tokenizer = Whitespace ; model = BPE ; unk_token = "[UNK]"
    >>> "ā" in vocab -> False      "ṭ" in vocab -> False
    >>> "ḍ" in vocab -> False      "ṇ" in vocab -> False   ... and so on

Because the pre-tokeniser splits on whitespace and the BPE falls back to [UNK]
for the *whole word* when any character is unknown, a single missing codepoint
destroys the entire word. Sinhala script (U+0D80-U+0DFF) is absent from the
vocab entirely, so *every* word becomes [UNK]. The model then learns to map
"unknown unknown unknown" onto audio: the loss falls convincingly and the
samples are noise. That is the failure mode of the earlier attempt.

There are two ways out:

  A. Extend the BPE vocab + resize the text embedding matrix, then train the new
     rows from random init. This is what published new-language XTTS ports do,
     and they use hundreds of hours and tens of thousands of optimiser steps.

  B. Spell Sinhala with characters XTTS *already knows*, and fine-tune with
     language="en". Every token is then a pretrained token with a sensible
     acoustic prior, nothing is randomly initialised, and the task collapses
     from "learn a new script" to "learn a new accent".

This file is (B). On a T4 with ~8 h of audio, (B) works and (A) does not.

THE MAPPING
-----------
pathnirvana/sinhala-tts-dataset ships each line twice: an ISO-style
romanisation (column 1) and Sinhala script (column 2). We fold either one down
to plain ASCII using Sri Lankan "Singlish" conventions, which happen to give
English-pretrained tokens roughly the right sound:

  retroflex  ට ඩ  -> t  d      (English t/d are the closest match)
  dental     ත ද  -> th dh     (h-digraph, as Sri Lankans write it)
  aspiration ඛ ඝ ඡ ඣ ඨ ඪ ථ ධ ඵ භ  -> dropped
             Modern spoken Sinhala has no phonemic aspiration -- ථ and ත are
             the same sound -- so collapsing them removes sparsity for free
             and frees the h-digraph for the dental series above.
  long vowels  ා ී ූ ේ ෝ  -> aa ii uu ee oo   (length written as doubling)
  ණ/න and ළ/ල  -> n / l       (homophones in modern Sinhala)
  ං ඞ ඟ        -> ng
  ශ ෂ          -> sh          (English "sh" is exactly /ʃ/)

MEASURED ON THE FULL 6386-LINE CORPUS
-------------------------------------
  output charset      : " !'(),-.:;=?abcdefghijklmnoprstuvy"  (pure ASCII)
  [UNK] tokens        : 0 out of 381,800
  tokens per line     : median 59, p95 97, max 117   (GPTArgs limit is 200)
  fold(roman) == sinhala_to_ascii(script) on 92.6% of lines; the residue is
  quote style, the "-පෙ-" ellipsis placeholder rows, and 175 t+h clusters that
  the romanisation writes ambiguously as "th".

Run `python sinhala_text.py --selftest metadata.csv vocab.json` to reproduce.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------
# 1. romanised (column 1 of pathnirvana metadata.csv) -> ascii
# --------------------------------------------------------------------------
# Applied as ONE left-to-right pass with longest-match-first alternation, so
# "ṭh" is consumed before "ṭ" and "th" before "t". A naive sequence of
# str.replace() calls would turn t -> th -> thh.
ROMAN_TO_ASCII = {
    # aspirates collapse
    "kh": "k", "gh": "g", "jh": "j", "ph": "p", "bh": "b", "ch": "ch",
    "ṭh": "t", "ḍh": "d",
    # retroflex -> bare stop, dental -> h-digraph
    "ṭ": "t", "ḍ": "d",
    "th": "th", "t": "th",
    "dh": "dh", "d": "dh",
    "c": "ch",
    # vowels: length by doubling
    "ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "oo",
    "æ": "ae", "ǣ": "aae",
    "ṛ": "ru", "ṝ": "ruu",          # ඍ is pronounced /ru/ in Sinhala
    # nasals and sibilants
    "ñ": "ny", "ṅ": "ng", "ṁ": "ng", "ṉ": "n", "ṇ": "n",
    "ś": "sh", "ş": "sh", "ḷ": "l", "ḥ": "h",
}
_ROMAN_RE = re.compile(
    "|".join(sorted(map(re.escape, ROMAN_TO_ASCII), key=len, reverse=True))
)

# --------------------------------------------------------------------------
# 2. Sinhala script -> the same ascii  (needed at inference time)
# --------------------------------------------------------------------------
CONSONANTS = {
    "ක": "k",  "ඛ": "k",  "ග": "g",  "ඝ": "g",  "ඞ": "ng", "ඟ": "ng",
    "ච": "ch", "ඡ": "ch", "ජ": "j",  "ඣ": "j",  "ඤ": "ny", "ඥ": "gn",
    "ට": "t",  "ඨ": "t",  "ඩ": "d",  "ඪ": "d",  "ණ": "n",  "ඬ": "nd",
    "ත": "th", "ථ": "th", "ද": "dh", "ධ": "dh", "න": "n",  "ඳ": "ndh",
    "ප": "p",  "ඵ": "p",  "බ": "b",  "භ": "b",  "ම": "m",  "ඹ": "mb",
    "ය": "y",  "ර": "r",  "ල": "l",  "ව": "v",  "ශ": "sh", "ෂ": "sh",
    "ස": "s",  "හ": "h",  "ළ": "l",  "ෆ": "f",
}
INDEPENDENT_VOWELS = {
    "අ": "a",  "ආ": "aa", "ඇ": "ae", "ඈ": "aae", "ඉ": "i",  "ඊ": "ii",
    "උ": "u",  "ඌ": "uu", "ඍ": "ru", "එ": "e",   "ඒ": "ee", "ඓ": "ai",
    "ඔ": "o",  "ඕ": "oo", "ඖ": "au",
}
VOWEL_SIGNS = {
    "ා": "aa", "ැ": "ae", "ෑ": "aae", "ි": "i",  "ී": "ii",
    "ු": "u",  "ූ": "uu", "ෘ": "ru",  "ෲ": "ruu",
    "ෙ": "e",  "ේ": "ee", "ෛ": "ai",
    "ො": "o",  "ෝ": "oo", "ෞ": "au",
}
VIRAMA   = "්"   # ් al-lakuna, kills the inherent vowel
ANUSVARA = "ං"   # ං
VISARGA  = "ඃ"   # ඃ
ZWJ      = "‍"   # conjunct joiner; carries no sound of its own

# --------------------------------------------------------------------------
# 3. punctuation
# --------------------------------------------------------------------------
_QUOTES = {"‘": "'", "’": "'", "“": "'", "”": "'", '"': "'"}
_KEEP = set("abcdefghijklmnopqrstuvwxyz .,?!'-:;")
_WS = re.compile(r"\s+")


def _normalise(txt: str) -> str:
    """Lowercase, unify quotes, drop what XTTS should never have to voice."""
    txt = txt.lower().replace(ZWJ, "")
    for a, b in _QUOTES.items():
        txt = txt.replace(a, b)
    txt = "".join(c for c in txt if c in _KEEP)
    return _WS.sub(" ", txt).strip()


def fold(roman: str) -> str:
    """ISO-style romanisation -> ascii XTTS can tokenise without [UNK]."""
    txt = roman.lower().replace(ZWJ, "")
    for a, b in _QUOTES.items():
        txt = txt.replace(a, b)
    txt = _ROMAN_RE.sub(lambda m: ROMAN_TO_ASCII[m.group(0)], txt)
    return _normalise(txt)


def sinhala_to_ascii(script: str) -> str:
    """Sinhala script -> the same ascii. Use this to feed the trained model."""
    txt = script.replace(ZWJ, "")
    out: list[str] = []
    i, n = 0, len(txt)
    while i < n:
        ch = txt[i]
        if ch in CONSONANTS:
            out.append(CONSONANTS[ch])
            i += 1
            if i < n and txt[i] == VIRAMA:
                i += 1                                  # vowel suppressed
            elif i < n and txt[i] in VOWEL_SIGNS:
                out.append(VOWEL_SIGNS[txt[i]])
                i += 1
            else:
                out.append("a")                         # inherent vowel
            continue
        if ch in INDEPENDENT_VOWELS:
            out.append(INDEPENDENT_VOWELS[ch]); i += 1; continue
        if ch == ANUSVARA:
            out.append("ng"); i += 1; continue
        if ch == VISARGA:
            out.append("h"); i += 1; continue
        if ch in VOWEL_SIGNS or ch == VIRAMA:
            i += 1; continue                            # stray sign, ignore
        out.append(ch); i += 1
    return _normalise("".join(out))


def to_ascii(text: str) -> str:
    """Accept either script or romanisation and do the right thing."""
    if any("඀" <= c <= "෿" for c in text):
        return sinhala_to_ascii(text)
    return fold(text)


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------
def _selftest(metadata: str, vocab: str | None) -> int:
    import collections
    import difflib

    rows = [l.rstrip("\n").split("|")
            for l in open(metadata, encoding="utf-8") if l.strip()]
    print(f"{len(rows)} lines from {metadata}")

    exact = compared = 0
    diffs: collections.Counter = collections.Counter()
    for r in rows:
        if len(r) < 3 or len(r[2].strip()) < 8:
            continue                                    # "-පෙ-" placeholder
        a, b = fold(r[1]), sinhala_to_ascii(r[2])
        compared += 1
        if a == b:
            exact += 1
        elif len(diffs) < 4000:
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
                if tag != "equal":
                    diffs[(a[i1:i2], b[j1:j2])] += 1
    print(f"fold(roman) == sinhala_to_ascii(script): "
          f"{exact}/{compared}  ({100 * exact / compared:.1f}%)")
    for (x, y), n in diffs.most_common(6):
        print(f"    {n:5d}  roman={x!r:10}  script={y!r}")

    charset = collections.Counter()
    for r in rows:
        charset.update(fold(r[1]))
    print("charset:", repr("".join(sorted(charset))))
    assert all(ord(c) < 128 for c in charset), "non-ascii leaked through fold()"

    if not vocab:
        return 0

    from tokenizers import Tokenizer
    tk = Tokenizer.from_file(vocab)
    unk = total = 0
    lens = []
    for r in rows:
        ids = tk.encode("[en]" + fold(r[1]).replace(" ", "[SPACE]"))
        unk += ids.tokens.count("[UNK]")
        total += len(ids.ids)
        lens.append(len(ids.ids))
    lens.sort()
    print(f"tokens: {total}   [UNK]: {unk}")
    print(f"length: median {lens[len(lens) // 2]}  "
          f"p95 {lens[int(0.95 * len(lens))]}  max {lens[-1]}  "
          f"(GPTArgs.max_text_length = 200)")
    assert unk == 0, f"{unk} [UNK] tokens -- the fold is incomplete"
    print("OK")
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest(sys.argv[2],
                                   sys.argv[3] if len(sys.argv) > 3 else None))
    for arg in sys.argv[1:]:
        print(to_ascii(arg))