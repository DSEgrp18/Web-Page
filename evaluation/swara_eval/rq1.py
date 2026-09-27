"""RQ1: does the verifier make generated questions safe?

Three conditions on the same held-out passages:

* ``full``: the product's graph, verifier and blind check both on.
* ``no_verifier``: every draft is kept. The verifier still rules on each one,
  after the fact, so its verdict can be compared with the teachers' ratings.
* ``no_blind_check``: the verifier on, the model's re-answer off.

Teachers rate every question blind to its condition. The verifier's **false
accepts** (it passed a question the raters judged ungrounded) are the safety
measure; its **false rejects** (it failed one they judged grounded) are the
cost. The switches used here are private arguments of ``draft_questions`` that
nothing outside ``evaluation/`` may pass.
"""

from __future__ import annotations

import csv
import json
import random
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from sinhala_documents.quiz import Candidate, Rejection, SourcePassage, verify
from sinhala_documents.quiz_graph import Transport, draft_questions

from .stats import bootstrap, krippendorff_alpha_nominal

CONDITIONS = ("full", "no_verifier", "no_blind_check")
ZWJ = "‍"
ZWNJ = "‌"

#: What a rater may say about a question. Only ``grounded`` counts as safe.
LABELS = ("grounded", "ungrounded", "unclear")


@dataclass(frozen=True)
class Drafted:
    """One question a condition produced, with the verifier's own verdict."""

    condition: str
    question: str
    options: list[str]
    answer: int
    passage: int
    quote: str
    verdict: str
    """``accepted``, or the rejection code the verifier gives it."""
    joiner_only: bool
    """Rejected only because of a joiner: it would pass with joiners removed."""


@dataclass(frozen=True)
class RunCost:
    condition: str
    calls: int
    seconds: float
    kept: int
    stopped: str


def _no_check(candidate: Candidate, passages: dict[int, SourcePassage]) -> Rejection | None:
    return None


def _without_joiners(text: str) -> str:
    return text.replace(ZWJ, "").replace(ZWNJ, "")


def joiner_only(candidate: Candidate, passages: dict[int, SourcePassage]) -> bool:
    """Whether the verifier rejects this only because of a joiner."""
    if verify(candidate, passages) is None:
        return False
    stripped = {n: replace(p, text=_without_joiners(p.text)) for n, p in passages.items()}
    bare = replace(
        candidate,
        question=_without_joiners(candidate.question),
        options=tuple(_without_joiners(o) for o in candidate.options),
        quote=_without_joiners(candidate.quote),
    )
    return verify(bare, stripped) is None


def run_condition(
    condition: str, passages: Sequence[SourcePassage], transport: Transport, *, target: int
) -> tuple[list[Drafted], RunCost]:
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition {condition!r}.")
    by_number = {p.number: p for p in passages}
    started = time.monotonic()
    result = draft_questions(
        passages,
        transport,
        target=target,
        _check=_no_check if condition == "no_verifier" else verify,
        _blind=condition != "no_blind_check",
    )
    seconds = time.monotonic() - started
    drafted = []
    for candidate in result.accepted:
        rejection = verify(candidate, by_number)
        drafted.append(
            Drafted(
                condition=condition,
                question=candidate.question,
                options=list(candidate.options),
                answer=candidate.answer,
                passage=candidate.passage,
                quote=candidate.quote,
                verdict=str(rejection) if rejection else "accepted",
                joiner_only=joiner_only(candidate, by_number),
            )
        )
    cost = RunCost(condition, result.calls, seconds, len(drafted), result.stopped)
    return drafted, cost


def save_run(folder: Path, drafted: list[Drafted], costs: list[RunCost]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "drafted.json").write_text(
        json.dumps([asdict(d) for d in drafted], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (folder / "costs.json").write_text(json.dumps([asdict(c) for c in costs], indent=1))


def rating_sheet(
    folder: Path, drafted: list[Drafted], passages: Sequence[SourcePassage], *, seed: int = 0
) -> None:
    """A blinded sheet for raters, and a separate key they never see.

    The sheet is shuffled and carries no condition and no verdict. The key maps
    each item back, and stays with the researcher.
    """
    by_number = {p.number: p for p in passages}
    order = list(range(len(drafted)))
    random.Random(seed).shuffle(order)
    with (
        (folder / "sheet.csv").open("w", newline="", encoding="utf-8-sig") as sheet,
        (folder / "key.csv").open("w", newline="", encoding="utf-8") as key,
    ):
        rows = csv.writer(sheet)
        keys = csv.writer(key)
        rows.writerow(["item", "passage", "question", "options", "marked_answer", "rating"])
        keys.writerow(["item", "condition", "verdict", "joiner_only"])
        for item, position in enumerate(order, start=1):
            d = drafted[position]
            rows.writerow(
                [
                    item,
                    by_number[d.passage].text if d.passage in by_number else "",
                    d.question,
                    " | ".join(f"{i}. {o}" for i, o in enumerate(d.options)),
                    d.answer,
                    "",
                ]
            )
            keys.writerow([item, d.condition, d.verdict, int(d.joiner_only)])


def read_ratings(paths: Sequence[Path]) -> dict[int, list[str | None]]:
    """One completed sheet per rater, in the same item numbering."""
    ratings: dict[int, list[str | None]] = {}
    for rater, path in enumerate(paths):
        with path.open(encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                label = (row.get("rating") or "").strip().lower() or None
                if label is not None and label not in LABELS:
                    raise ValueError(f"{path}: item {row['item']}: {label!r} is not a label.")
                ratings.setdefault(int(row["item"]), [None] * len(paths))[rater] = label
    return ratings


def majority(labels: Sequence[str | None]) -> str | None:
    counted = Counter(label for label in labels if label)
    if not counted:
        return None
    (top, count), *rest = counted.most_common()
    return None if rest and rest[0][1] == count else top


def analyse(key_path: Path, ratings: dict[int, list[str | None]], costs: list[RunCost]) -> dict:
    """Grounded rate per condition, rater agreement, and the verifier's errors."""
    with key_path.open(encoding="utf-8") as handle:
        key = list(csv.DictReader(handle))
    per_condition: dict[str, list[float]] = {c: [] for c in CONDITIONS}
    confusion = Counter()
    codes = Counter()
    joiner_rejections = 0
    for row in key:
        judged = majority(ratings.get(int(row["item"]), []))
        accepted = row["verdict"] == "accepted"
        if not accepted:
            codes[row["verdict"]] += 1
            joiner_rejections += row["joiner_only"] == "1"
        if judged is None or judged == "unclear":
            continue
        grounded = judged == "grounded"
        per_condition[row["condition"]].append(1.0 if grounded else 0.0)
        confusion[(accepted, grounded)] += 1
    accepted_total = confusion[(True, True)] + confusion[(True, False)]
    rejected_total = confusion[(False, True)] + confusion[(False, False)]
    return {
        "grounded_rate": {c: bootstrap(v).as_dict() for c, v in per_condition.items()},
        "rater_agreement_alpha": krippendorff_alpha_nominal(list(ratings.values())),
        "verifier": {
            "accepted_and_grounded": confusion[(True, True)],
            "false_accepts": confusion[(True, False)],
            "false_rejects": confusion[(False, True)],
            "rejected_and_ungrounded": confusion[(False, False)],
            "false_accept_rate": confusion[(True, False)] / accepted_total
            if accepted_total
            else None,
            "false_reject_rate": confusion[(False, True)] / rejected_total
            if rejected_total
            else None,
        },
        "rejection_codes": dict(codes),
        "rejections_caused_by_joiners_only": joiner_rejections,
        "cost": {
            c.condition: {
                "model_calls": c.calls,
                "seconds": round(c.seconds, 1),
                "questions": c.kept,
                "calls_per_question": round(c.calls / c.kept, 2) if c.kept else None,
                "stopped_by": c.stopped,
            }
            for c in costs
        },
    }
