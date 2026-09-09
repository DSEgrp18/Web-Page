"""Sinhala cardinal numbers, written out as words.

Why this exists
---------------
The vendored text front end deletes every digit (see
``tests/test_text_frontend_characterisation.py``). For a document reader that is
serious: ``"පිටුව 42 බලන්න"`` is narrated as ``"pituva balanna"``, so the
listener hears a fluent sentence with the page number simply missing and nothing
tells them anything was lost.

The front end cannot be fixed, because its behaviour is what the model heard
during training. Numbers therefore have to be written out as Sinhala words
*before* the front end runs, while the digits still exist.

.. warning::

   **The word forms in this module need review by a native Sinhala speaker.**

   They were assembled from standard spoken Sinhala cardinal forms, and the
   structure — separate standalone and combining forms for tens, hundreds and
   thousands — is the part worth checking hardest. ``විස්ස`` alone but ``විසි``
   before another word is the pattern the tables encode; if any individual form
   is wrong, correcting the table here fixes every number that uses it.

   Until that review happens, treat narrated numbers as unverified. The tables
   are deliberately plain dictionaries so a reviewer can correct them without
   reading any logic.

Scope
-----
Supported: integers 0–9999, which covers years, page and section numbers, list
numbering, and most figures in a school textbook.

Deliberately not supported: 10,000 and above. Sinhala composition with ``ලක්ෂ``
and larger units is more intricate than the ranges below, and guessing at it
would produce confident-sounding errors in exactly the place they are hardest to
notice. Callers handle the out-of-range case explicitly rather than receiving a
plausible wrong answer — see :func:`cardinal` and the caller in ``normalize.py``.

Also out of scope for now, and left to later increments: ordinals
(``1වන``), currency, dates, times, and fractions.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Word tables. Native-speaker review starts here.
# --------------------------------------------------------------------------

ZERO = "බින්දුව"

UNITS = {
    1: "එක",
    2: "දෙක",
    3: "තුන",
    4: "හතර",
    5: "පහ",
    6: "හය",
    7: "හත",
    8: "අට",
    9: "නවය",
}

# 10-19 are irregular and are listed individually rather than composed.
TEENS = {
    10: "දහය",
    11: "එකොළහ",
    12: "දොළහ",
    13: "දහතුන",
    14: "දාහතර",
    15: "පහළොව",
    16: "දහසය",
    17: "දාහත",
    18: "දහඅට",
    19: "දහනවය",
}

# Tens have two forms: one used alone, one used before a following unit.
# 20 is විස්ස on its own but විසි in "විසි එක" (21).
TENS_ALONE = {
    20: "විස්ස",
    30: "තිහ",
    40: "හතළිහ",
    50: "පනහ",
    60: "හැට",
    70: "හැත්තෑව",
    80: "අසූව",
    90: "අනූව",
}
TENS_BEFORE_UNIT = {
    20: "විසි",
    30: "තිස්",
    40: "හතළිස්",
    50: "පනස්",
    60: "හැට",
    70: "හැත්තෑ",
    80: "අසූ",
    90: "අනූ",
}

# Same standalone/combining split for hundreds: 300 is තුන්සියය alone,
# තුන්සිය in "තුන්සිය පනහ" (350).
HUNDREDS_ALONE = {
    1: "සියය",
    2: "දෙසියය",
    3: "තුන්සියය",
    4: "හාරසියය",
    5: "පන්සියය",
    6: "හයසියය",
    7: "හත්සියය",
    8: "අටසියය",
    9: "නවසියය",
}
HUNDREDS_BEFORE_REST = {
    1: "එකසිය",
    2: "දෙසිය",
    3: "තුන්සිය",
    4: "හාරසිය",
    5: "පන්සිය",
    6: "හයසිය",
    7: "හත්සිය",
    8: "අටසිය",
    9: "නවසිය",
}

# And again for thousands: 2000 is දෙදහස alone, දෙදහස් in "දෙදහස් විසි හතර"
# (2024, the form a year takes).
THOUSANDS_ALONE = {
    1: "දහස",
    2: "දෙදහස",
    3: "තුන්දහස",
    4: "හාරදහස",
    5: "පන්දහස",
    6: "හයදහස",
    7: "හත්දහස",
    8: "අටදහස",
    9: "නවදහස",
}
THOUSANDS_BEFORE_REST = {
    1: "එක්දහස්",
    2: "දෙදහස්",
    3: "තුන්දහස්",
    4: "හාරදහස්",
    5: "පන්දහස්",
    6: "හයදහස්",
    7: "හත්දහස්",
    8: "අටදහස්",
    9: "නවදහස්",
}

# The decimal point, read before the digits that follow it.
DECIMAL_POINT = "දශම"

# "සියයට පනහ" for 50%. Note the word order reverses: the marker precedes the
# number in Sinhala, where "%" follows it in the written form.
PERCENT = "සියයට"

MIN_SUPPORTED = 0
MAX_SUPPORTED = 9999


class NumberOutOfRangeError(ValueError):
    """Raised for integers this module deliberately does not attempt.

    Callers must decide what to do rather than receiving a guess. Silently
    producing a wrong Sinhala form would be worse than the digit deletion this
    module exists to fix, because it would sound correct.
    """


def _under_hundred(n: int) -> str:
    """1-99."""
    if n < 10:
        return UNITS[n]
    if n < 20:
        return TEENS[n]
    tens, unit = divmod(n, 10)
    if unit == 0:
        return TENS_ALONE[tens * 10]
    return f"{TENS_BEFORE_UNIT[tens * 10]} {UNITS[unit]}"


def _under_thousand(n: int) -> str:
    """1-999."""
    hundreds, rest = divmod(n, 100)
    if hundreds == 0:
        return _under_hundred(rest)
    if rest == 0:
        return HUNDREDS_ALONE[hundreds]
    return f"{HUNDREDS_BEFORE_REST[hundreds]} {_under_thousand(rest)}"


def cardinal(n: int) -> str:
    """Write a non-negative integer as Sinhala words.

    Raises :class:`NumberOutOfRangeError` outside 0-9999. That is deliberate:
    see the module docstring.
    """
    if n < MIN_SUPPORTED or n > MAX_SUPPORTED:
        raise NumberOutOfRangeError(
            f"{n} is outside the supported range {MIN_SUPPORTED}-{MAX_SUPPORTED}"
        )
    if n == 0:
        return ZERO
    thousands, rest = divmod(n, 1000)
    if thousands == 0:
        return _under_thousand(rest)
    if rest == 0:
        return THOUSANDS_ALONE[thousands]
    return f"{THOUSANDS_BEFORE_REST[thousands]} {_under_thousand(rest)}"


def digits_individually(digits: str) -> str:
    """Read digits one at a time: "42" as "හතර දෙක".

    Used for the digits after a decimal point, where reading "14" as "fourteen"
    would be wrong, and as the explicit fallback for numbers too large for
    :func:`cardinal`. Reading a long number digit by digit is clumsy, but it is
    honest and loses nothing, which deleting it is not.
    """
    return " ".join(ZERO if d == "0" else UNITS[int(d)] for d in digits)
