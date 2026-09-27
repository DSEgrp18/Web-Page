"""Retrieval, RQ3 and RQ4 runners, and the rule that only aggregates are written."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile

from swara_eval import rq3, rq4
from swara_eval.books import prepare
from swara_eval.results import NotAnAggregate, write_result
from swara_eval.retrieval import Question, hit, recall_at

WORKER_TESTS = Path(__file__).resolve().parents[2] / "services" / "worker" / "tests"
sys.path.insert(0, str(WORKER_TESTS))
from pdf_fixtures import build_pdf, sinhala_page  # noqa: E402


class TestRetrieval:
    def test_a_question_is_recalled_by_any_gold_page(self) -> None:
        assert hit([4, 2], frozenset({2}))
        assert not hit([4, 3], frozenset({2}))

    def test_recall_over_a_real_prepared_book(self, tmp_path: Path) -> None:
        (tmp_path / "book.pdf").write_bytes(build_pdf([sinhala_page()]))
        words = prepare(tmp_path / "book.pdf").segments[0].display_text.split()
        questions = [
            Question(" ".join(words[:3]), "book.pdf", frozenset({0})),
            Question("පොතේ නැති දෙයක්", "book.pdf", frozenset()),
        ]

        result = recall_at(questions, tmp_path, k=5)

        assert result["answerable"] == 1 and result["unanswerable"] == 1
        assert result["recall_at_5"]["value"] == 1.0


def write_csv(path: Path, rows: list[list[object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    return path


class TestRq3:
    def test_summarises_per_task_without_naming_anyone(self, tmp_path: Path) -> None:
        sessions = write_csv(
            tmp_path / "sessions.csv",
            [
                ["participant", "task", "completed", "seconds", "assists", "errors", "technology"],
                ["p1", "find_and_hear_chapter", 1, 40, 0, 0, "NVDA"],
                ["p2", "find_and_hear_chapter", 0, 300, 2, 1, "TalkBack"],
            ],
        )
        umux = write_csv(
            tmp_path / "umux.csv", [["participant", "capabilities", "ease"], ["p1", 7, 7]]
        )

        result = rq3.summarise(sessions, umux)

        task = result["tasks"]["find_and_hear_chapter"]
        assert task["completion"]["value"] == 0.5 and task["median_seconds_when_completed"] == 40
        assert result["umux_lite"]["value"] == 100
        assert "p1" not in json.dumps(result)

    def test_an_unknown_task_is_refused(self, tmp_path: Path) -> None:
        sessions = write_csv(
            tmp_path / "s.csv",
            [
                ["participant", "task", "completed", "seconds", "assists", "errors"],
                ["p1", "something_else", 1, 1, 0, 0],
            ],
        )

        with pytest.raises(ValueError):
            rq3.summarise(sessions)


def clips(folder: Path, count: int = 3) -> Path:
    folder.mkdir()
    rate = 24_000
    t = np.arange(rate * 2) / rate
    for n in range(count):
        tone = 0.3 * np.sin(2 * np.pi * (150 + 20 * n) * t) * (1 + np.sin(2 * np.pi * 3 * t))
        soundfile.write(folder / f"{n}.wav", tone.astype(np.float32), rate)
    return folder


class TestRq4:
    def test_opus_is_far_smaller_per_hour(self, tmp_path: Path) -> None:
        result = rq4.sizes(clips(tmp_path / "clips"))

        per_hour = result["megabytes_per_hour"]
        assert per_hour["opus"] * 5 < per_hour["wav"]

    def test_the_listening_set_is_blind_and_scored_against_its_key(self, tmp_path: Path) -> None:
        out = tmp_path / "listening"
        rq4.pairs(clips(tmp_path / "clips"), out)
        with (out / "key.csv").open(encoding="utf-8") as handle:
            key = {row["pair"]: row["opus_is"] for row in csv.DictReader(handle)}
        # A listener who always picks the WAV one.
        wav_side = {pair: "b" if opus == "a" else "a" for pair, opus in key.items()}
        sheet = write_csv(
            tmp_path / "sheet.csv",
            [["pair", "preferred (a, b or same)"]] + [[p, s] for p, s in wav_side.items()],
        )

        result = rq4.listening([sheet], out / "key.csv")

        assert result["preferred_wav"] == 3 and result["preferred_opus"] == 0
        assert all(len(list(out.glob(f"00{n}-*.wav"))) == 2 for n in (1, 2, 3))

    def test_latency_percentiles_carry_what_was_declared(self) -> None:
        summary = rq4.latency_summary(
            [1.0, 2.0, 3.0], label="pre-rendered", declared={"device": "Galaxy A04"}
        )

        assert summary["p50_seconds"] == 2.0 and summary["declared"]["device"] == "Galaxy A04"


class TestResults:
    def test_a_row_about_a_person_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(NotAnAggregate):
            write_result("x", {"rows": [{"participant": "p1", "seconds": 3}]}, folder=tmp_path)

    def test_an_aggregate_is_written_with_its_commit(self, tmp_path: Path) -> None:
        path = write_result("x", {"completion": 0.9}, folder=tmp_path)

        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["completion"] == 0.9 and "generated_at" in body
