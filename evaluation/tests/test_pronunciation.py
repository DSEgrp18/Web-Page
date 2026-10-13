"""The pronunciation kit: candidates are faithful, the page is blind, scores add up."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest
from sinhala_tts.normalize import to_model_input

from swara_eval.pronunciation import (
    VARIANTS,
    Tokens,
    build_page,
    candidates,
    score,
    write_candidates,
)

BUNDLE = Path(__file__).resolve().parents[2] / "models" / "xtts_si_female"


def test_todays_spelling_is_exactly_what_the_product_speaks() -> None:
    for row in candidates():
        if row.variant == "current":
            assert row.ascii_word == to_model_input(row.word)


def test_only_the_sanyaka_ga_changes_between_variants() -> None:
    rows = [r for r in candidates() if r.word == "ගොඩනඟයි"]
    spellings = {r.variant: r.ascii_word for r in rows}
    assert spellings == {
        "current": "godanangayi",
        "nasal-stop": "godananggayi",
        "syllable-break": "godanan-gayi",
        "no-nasal": "godanagayi",
    }
    # The ordinary න before it is untouched in every variant.
    assert all(s.startswith("godana") for s in spellings.values())


def test_every_word_is_in_the_same_carrier_sentence() -> None:
    for row in candidates():
        assert row.model_text == f"{row.ascii_word} yana vachanaya."


@pytest.mark.skipif(not (BUNDLE / "vocab.json").is_file(), reason="model bundle not present")
def test_every_candidate_tokenises_without_unk(tmp_path: Path) -> None:
    rows = write_candidates(tmp_path, Tokens(BUNDLE / "vocab.json", BUNDLE / "config.json"))
    assert len(rows) == len(candidates())
    assert all(int(r["unk_count"]) == 0 for r in rows)
    assert all(int(r["token_count"]) <= int(r["token_limit"]) for r in rows)
    ganga = next(r for r in rows if r["word"] == "ගඟ" and r["variant"] == "current")
    assert ganga["word_tokens"] == "gang a"


def fake_run(tmp_path: Path) -> Path:
    """A results.csv as the GPU run writes it, with stand-in WAV bytes."""
    run = tmp_path / "run"
    (run / "audio").mkdir(parents=True)
    rows = []
    for number, (candidate, seed) in enumerate(
        (c, s) for c in candidates() for s in ("101", "202")
    ):
        path = f"audio/{number:03d}.wav"
        (run / path).write_bytes(f"RIFF{number}".encode())
        rows.append(
            {
                "word": candidate.word,
                "group": candidate.group,
                "variant": candidate.variant,
                "ascii_word": candidate.ascii_word,
                "seed": seed,
                "output_path": path,
            }
        )
    with (run / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return run / "results.csv"


def test_the_page_says_nothing_about_which_spelling_made_which_clip(tmp_path: Path) -> None:
    page = build_page(fake_run(tmp_path), tmp_path / "test")
    text = page.read_text(encoding="utf-8")

    for row in candidates():
        assert row.ascii_word not in text
    for variant in VARIANTS:
        assert variant not in text
    names = re.findall(r'src="clips/([0-9a-f]{12}\.wav)"', text)
    assert names and all((page.parent / "clips" / n).is_file() for n in names)

    key = json.loads((tmp_path / "test" / "key.json").read_text(encoding="utf-8"))
    assert set(names) <= set(key)
    # One question per word and seed, with every variant, and one per check word.
    assert text.count("Which says it most correctly?") == 8 * 2
    assert text.count("Is it said correctly?") == 6


def test_scores_count_choices_none_and_checks(tmp_path: Path) -> None:
    out = tmp_path / "test"
    page = build_page(fake_run(tmp_path), out)
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    text = page.read_text(encoding="utf-8")

    def clip_for(word: str, variant: str) -> str:
        return next(n for n, v in key.items() if v["word"] == word and v["variant"] == variant)

    question = re.search(r'fieldset id="(q\d+)"><legend><span lang="si">ගඟ</span>', text)
    assert question
    answers = {
        "a": {"q1": clip_for("ගඟ", "nasal-stop"), "q2": "none:" + clip_for("අඟල", "current")},
        "b": {"q1": clip_for("ගඟ", "nasal-stop"), "q3": clip_for("ගංගා", "current") + "|yes"},
    }
    paths = []
    for rater, given in answers.items():
        path = tmp_path / f"answers-{rater}.json"
        path.write_text(json.dumps({"rater": rater, "answers": given}), encoding="utf-8")
        paths.append(path)

    result = score(out / "key.json", paths)
    assert result["listeners"] == 2
    assert result["preferred"]["ගඟ"] == {"nasal-stop": 2}
    assert result["preferred"]["අඟල"] == {"none": 1}
    assert result["regression"]["ගංගා"] == {"yes": 1, "no": 0}
    assert result["preferred_overall"] == {"nasal-stop": 2, "none": 1}
