"""The ablation switches never leave the evaluation kit.

``draft_questions(_check=..., _blind=...)`` turns off the verifier or the blind
check for RQ1. If product code ever passed either, a question the verifier
rejected could reach a student. This fails the build the moment it does.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWITCH = re.compile(r"\b_(check|blind)\s*=")


def test_only_the_evaluation_kit_passes_the_ablation_switches() -> None:
    offenders = []
    for folder in ("services", "apps"):
        for path in (ROOT / folder).rglob("*.py"):
            if "site-packages" in path.parts or ".venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for number, line in enumerate(text.splitlines(), start=1):
                if SWITCH.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    # Declaring the parameters (``_check: Callable = verify``) does not match;
    # only passing one does, and nothing outside evaluation/ may.
    assert offenders == [], "\n".join(offenders)
