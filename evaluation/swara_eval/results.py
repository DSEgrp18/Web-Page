"""Where results go, and the rule for what may be committed.

Raw material (drafted questions, ratings, session logs, timings, audio) goes
in ``evaluation/data/``, which Git ignores. Only aggregates go in
``evaluation/results/``: counts, rates, intervals and percentiles, never a row
per person or per rated item. :func:`write_result` refuses anything that looks
like a row about a person, and ``scripts/verify-repo-hygiene.sh`` checks again
before anything is merged.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
RESULTS = HERE / "results"

#: Keys that only a per-person or per-item row would have.
FORBIDDEN_KEYS = frozenset(
    {"participant", "participant_id", "rater", "rater_id", "name", "email", "item_id", "text"}
)


class NotAnAggregate(ValueError):
    """A result carried something that identifies a person or an item."""


def _check(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise NotAnAggregate(f"{path}{key}: results hold aggregates only.")
            _check(inner, f"{path}{key}.")
    elif isinstance(value, list):
        for position, inner in enumerate(value):
            _check(inner, f"{path}{position}.")


def _commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=HERE
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_result(name: str, payload: dict[str, Any], *, folder: Path = RESULTS) -> Path:
    """Write one aggregate result as JSON, with when and from which commit."""
    _check(payload)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    body = {"generated_at": datetime.now(UTC).isoformat(), "commit": _commit(), **payload}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
