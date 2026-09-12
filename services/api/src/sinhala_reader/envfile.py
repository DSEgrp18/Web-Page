"""Read a ``.env`` file into the environment, without overriding it.

Every setting in this service is read from :data:`os.environ` at the composition
root. That is the right place for them to come from — it is what a container,
a systemd unit and a CI job all speak — but it makes local development awkward:
the reader needs an identity mode, an origin list, a model directory and now a
structure provider's key, and typing four exports before every ``uvicorn`` is
how people end up committing a shell script with a key in it.

So this reads a file that :file:`.gitignore` refuses to track. Three rules, each
of which exists to prevent a specific accident:

**The real environment always wins.** A value already in :data:`os.environ` is
never replaced. A stale ``.env`` on a server must not be able to override what
the deployment set, and ``SINHALA_READER_AUTH=development`` left in a file must
not be able to turn off authentication somewhere it matters.

**Nothing is required.** A missing file is not an error. The file is a
convenience for people, and the service must behave identically without one.

**Nothing is interpolated.** No ``$VAR`` expansion and no command substitution:
this file may hold a credential, and a format that can reference other values is
a format that can be made to leak them.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The file name, at the repository root. Ignored by Git; see .gitignore.
ENV_FILENAME = ".env"


def find_env_file(start: Path | None = None) -> Path | None:
    """The nearest ``.env`` at or above ``start``, or ``None``.

    Walks upwards because the service is run from several directories — the
    repository root, ``services/api``, and a container's workdir — and the file
    belongs to the checkout rather than to whichever of those a person chose.
    """
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines.

    Understands blank lines, ``#`` comments, a leading ``export``, and single or
    double quotes around a value. Quotes are stripped only as a matched pair, so
    a key that genuinely contains a quote survives.

    A line without ``=`` is skipped rather than raising. A malformed line in a
    developer convenience file should not stop the server from starting, and the
    alternative — guessing what was meant — is worse than ignoring it.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(path: Path | None = None, *, environ: dict[str, str] | None = None) -> list[str]:
    """Load ``path`` into ``environ``, skipping names already set.

    Returns the names it set, so a caller can log *that* a value came from the
    file without logging the value — which may be a credential.
    """
    target = os.environ if environ is None else environ
    path = path or find_env_file()
    if path is None:
        return []
    try:
        # utf-8-sig, not utf-8: Notepad, PowerShell's Out-File and several
        # Windows editors write a byte order mark, and this repository is
        # developed on Windows. Read as plain utf-8 the mark becomes part of the
        # first key, so GEMINI_API_KEY on line one silently becomes a name
        # nothing looks up — the file is present, the key is in it, and the
        # service behaves as though it were unset.
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        # Unreadable is treated as absent, for the same reason a missing file is:
        # this must never be the thing that stops the service from starting.
        return []

    applied: list[str] = []
    for key, value in parse_env(text).items():
        if key in target:
            continue
        target[key] = value
        applied.append(key)
    return applied
