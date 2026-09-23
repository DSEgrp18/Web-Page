"""Codes a person types: teacher invitations, and account recovery.

A code here is read aloud by a screen reader one character at a time, copied
from a message, and typed on a phone, so it is built for that:

* **No look-alikes.** 0 and O, 1, I and L are left out, so neither a reader
  nor a font can confuse them.
* **Groups of four,** joined by hyphens, so a screen reader pauses and a
  reader can keep their place.
* **Forgiving input.** Case, spaces and hyphens are ignored when a code is
  checked; what matters is the characters.

Only the SHA-256 of a code is stored, as for session tokens: a code is random
enough that there is no dictionary to try, and the store never needs to show
one again.
"""

from __future__ import annotations

import hashlib
import secrets

#: 31 characters: A-Z and 2-9 without O, I and L, 0 and 1.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

GROUP = 4


def new_code(groups: int = 3) -> str:
    """A fresh code of ``groups`` groups of four. Three groups is about 59 bits."""
    characters = "".join(secrets.choice(ALPHABET) for _ in range(groups * GROUP))
    return "-".join(characters[i : i + GROUP] for i in range(0, len(characters), GROUP))


def normalise(code: str) -> str:
    """The characters that count: upper case, without spaces or hyphens."""
    return "".join(character for character in code.upper() if character not in " -\t\n")


def code_hash(code: str) -> str:
    """What is stored and looked up, for a code as typed."""
    return hashlib.sha256(normalise(code).encode("utf-8")).hexdigest()
