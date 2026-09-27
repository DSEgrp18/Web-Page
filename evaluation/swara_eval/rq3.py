"""RQ3: can blind and low-vision students complete the loop on their own?

The facilitator records one row per participant and task in a sessions CSV:
``participant, task, completed (0/1), seconds, assists, errors, technology``,
and the two UMUX-Lite items per participant in a second CSV:
``participant, capabilities, ease`` (1–7). Both stay in ``evaluation/data/``.

What leaves that folder is per task and per technology, never per person, and
makes no claim about learning.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .stats import bootstrap, percentile, umux_lite

TASKS = (
    "find_and_hear_chapter",
    "ask_and_hear_source",
    "quiz_and_hear_missed_source",
    "find_what_to_revise",
    "teacher_publish",
)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def summarise(sessions: Path, umux: Path | None = None) -> dict:
    by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    technologies: set[str] = set()
    participants: set[str] = set()
    for row in _rows(sessions):
        if row["task"] not in TASKS:
            raise ValueError(f"Unknown task {row['task']!r}; the protocol names {TASKS}.")
        by_task[row["task"]].append(row)
        technologies.add(row.get("technology", "").strip() or "unrecorded")
        participants.add(row["participant"])

    tasks = {}
    for task in TASKS:
        rows = by_task.get(task, [])
        if not rows:
            continue
        done = [float(r["completed"]) for r in rows]
        seconds = [float(r["seconds"]) for r in rows if r["completed"] == "1"]
        tasks[task] = {
            "attempts": len(rows),
            "completion": bootstrap(done).as_dict(),
            "median_seconds_when_completed": percentile(seconds, 50) if seconds else None,
            "assists_per_attempt": sum(int(r["assists"]) for r in rows) / len(rows),
            "errors_per_attempt": sum(int(r["errors"]) for r in rows) / len(rows),
        }

    result: dict = {
        "participants": len(participants),
        "technologies": sorted(technologies),
        "tasks": tasks,
        "claim": "Formative usability only; no claim about learning gains.",
    }
    if umux is not None:
        scores = [umux_lite(int(r["capabilities"]), int(r["ease"])) for r in _rows(umux)]
        result["umux_lite"] = {
            **bootstrap(scores).as_dict(),
            "note": "Sinhala translation of UMUX-Lite not validated.",
        }
    return result
