"""Stable codes for pipeline notes, so the interface can translate them.

The extractor used to store English sentences. Those landed inside a Sinhala
page marked ``lang="en"``, which a screen reader could switch voice for but
a Sinhala-only reader still could not understand. Codes travel through the
API; each UI language maps them. Unknown or legacy English prose is still
accepted so older stored documents keep working.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

PREFIX = "note:"


def make(code: str, **params: object) -> str:
    """``note:garbled_native`` or ``note:legacy_unsupported?name=FMKaputa``."""
    if not params:
        return f"{PREFIX}{code}"
    query = urlencode({key: str(value) for key, value in params.items()})
    return f"{PREFIX}{code}?{query}"


def parse(note: str) -> tuple[str, dict[str, str]] | None:
    if not note.startswith(PREFIX):
        return None
    parts = urlsplit("http://_/" + note[len(PREFIX) :])
    code = parts.path.lstrip("/")
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    return code, params
