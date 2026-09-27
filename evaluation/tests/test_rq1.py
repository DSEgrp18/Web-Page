"""RQ1's three conditions, the blinded sheet, and the analysis, with a fake model."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from sinhala_documents.quiz import Candidate, SourcePassage  # noqa: E402

from swara_eval.rq1 import (  # noqa: E402
    RunCost,
    analyse,
    joiner_only,
    majority,
    rating_sheet,
    read_ratings,
    run_condition,
)

SENTENCE = "ශ්‍රී ලංකාවේ අගනුවර ශ්‍රී ජයවර්ධනපුර කෝට්ටේ වේ."
TEXT = SENTENCE + " කොළඹ ප්‍රධාන වරාය නගරය වන අතර වෙළඳාමේ කේන්ද්‍රස්ථානය ද වේ. " * 2
PASSAGES = [SourcePassage(n, TEXT, n, str(n), (f"s{n}",)) for n in range(1, 9)]
GOOD = {
    "question": "ශ්‍රී ලංකාවේ අගනුවර කුමක්ද?",
    "options": ["ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "මහනුවර", "ගාල්ල", "යාපනය"],
    "answer": 0,
    "quote": SENTENCE,
}
UNGROUNDED = {**GOOD, "quote": "පොතේ නැති වාක්‍යයකි."}


def model(draft: dict, choice: int = 0):
    def send(system: str, user: str) -> dict:
        blind = "Answer the multiple-choice question" in system
        return {"choice": choice} if blind else dict(draft)

    return send


def test_the_full_graph_keeps_only_what_the_verifier_passes() -> None:
    kept, cost = run_condition("full", PASSAGES, model(UNGROUNDED), target=2)

    assert kept == [] and cost.calls > 0


def test_without_the_verifier_every_draft_is_kept_and_judged_after() -> None:
    kept, _ = run_condition("no_verifier", PASSAGES, model(UNGROUNDED), target=2)

    assert kept and {d.verdict for d in kept} == {"quote_not_in_passage"}


def test_without_the_blind_check_the_model_is_never_asked() -> None:
    asked: list[str] = []

    def send(system: str, user: str) -> dict:
        asked.append(system)
        return dict(GOOD)

    kept, _ = run_condition("no_blind_check", PASSAGES, send, target=2)

    assert len(kept) == 2 and len(asked) == 2
    assert all(d.verdict == "accepted" for d in kept)


def test_a_joiner_only_rejection_is_recognised() -> None:
    passages = {1: SourcePassage(1, TEXT, 1, "1", ("s1",))}
    # The quote as the book has it, but with its joiners dropped.
    stripped = Candidate(
        question=GOOD["question"],
        options=tuple(GOOD["options"]),
        answer=0,
        passage=1,
        quote=SENTENCE.replace("‍", ""),
    )

    assert joiner_only(stripped, passages)


def test_a_tie_between_raters_is_no_majority() -> None:
    assert majority(["grounded", "ungrounded"]) is None
    assert majority(["grounded", "grounded", "ungrounded"]) == "grounded"


def test_the_sheet_is_blind_and_the_analysis_counts_the_verifiers_errors(
    tmp_path: Path,
) -> None:
    kept, cost = run_condition("no_verifier", PASSAGES, model(UNGROUNDED), target=2)
    good, good_cost = run_condition("full", PASSAGES, model(GOOD), target=2)
    rating_sheet(tmp_path, kept + good, PASSAGES)

    with (tmp_path / "sheet.csv").open(encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    assert "condition" not in header and "verdict" not in header

    with (tmp_path / "key.csv").open(encoding="utf-8") as handle:
        key = list(csv.DictReader(handle))
    # Two raters. They call the verifier's rejections grounded (false rejects)
    # and its acceptances ungrounded (false accepts), so both counts are exercised.
    for rater in ("a", "b"):
        with (tmp_path / f"{rater}.csv").open("w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["item", "rating"])
            for row in key:
                accepted = row["verdict"] == "accepted"
                writer.writerow([row["item"], "ungrounded" if accepted else "grounded"])

    ratings = read_ratings([tmp_path / "a.csv", tmp_path / "b.csv"])
    result = analyse(tmp_path / "key.csv", ratings, [cost, good_cost])

    assert result["verifier"]["false_accepts"] == len(good)
    assert result["verifier"]["false_rejects"] == len(kept)
    assert result["rater_agreement_alpha"] == 1.0
    assert result["rejection_codes"] == {"quote_not_in_passage": len(kept)}
    assert result["cost"]["full"]["questions"] == len(good)


def test_a_label_outside_the_rubric_is_refused(tmp_path: Path) -> None:
    sheet = tmp_path / "r.csv"
    sheet.write_text("item,rating\n1,maybe\n", encoding="utf-8")

    with pytest.raises(ValueError):
        read_ratings([sheet])


def test_costs_round_trip() -> None:
    assert RunCost("full", 3, 1.5, 1, "done").calls == 3
