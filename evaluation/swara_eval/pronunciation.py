"""Prenasalised consonants: candidate spellings, a blind listening test, scores.

The question: the bundled converter writes ඟ as ``ng``, which the tokenizer
reads as the English token ``gang``, losing the ``g`` after the nasal. ඹ, ඳ
and ඬ keep their stop (``mb``, ``ndh``, ``nd``). Does another spelling of ඟ
sound more like Sinhala to native listeners, without retraining?

Three steps, the middle one on a GPU (``pronunciation_modal.py``):

1. ``candidates``: for each test word, today's spelling and a few
   alternatives, each placed in the same carrier sentence, tokenised and
   checked for [UNK] and length. No audio. Zero [UNK] tokens means the model
   can *read* a spelling, never that it sounds right.
2. GPU: every row spoken with the same reference clip, settings and seeds.
3. ``page`` and ``score``: a page where listeners pick the most accurate
   version without seeing which spelling made it, and the tally.

Nothing here changes the converter, the model or the product's output. A
spelling that wins goes, word by word, into the opt-in override dictionary
(``services/tts/src/sinhala_tts/overrides.py``), a separate variant.
"""

from __future__ import annotations

import csv
import html
import json
import random
import secrets
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from sinhala_tts.vendor.sinhala_text import sinhala_to_ascii

#: The letter under test.
SANYAKA_GA = "ඟ"

#: What replaces the nasal part of ඟ in each candidate. Applied only to ඟ,
#: only in the test word: never globally, and never by inserting vowels.
VARIANTS: dict[str, tuple[str, str]] = {
    "current": ("n", "Today's converter: ඟ -> ng, read as the English token 'gang'."),
    "nasal-stop": (
        "ng",
        "ඟ -> ngg: nasal then g, as ඹ -> mb, ඳ -> ndh and ඬ -> nd already keep their stop.",
    ),
    "syllable-break": (
        "n-",
        "ඟ -> n-g: a break before g, so the tokenizer cannot merge 'ng' into 'gang'.",
    ),
    "no-nasal": ("", "ඟ -> g: a control. Prenasalisation removed entirely; expected worse."),
}

#: Words with ඟ, common in school texts. (word, English gloss)
PRENASAL_WORDS: list[tuple[str, str]] = [
    ("ගඟ", "river"),
    ("ගඟුල", "stream"),
    ("අඟල", "inch"),
    ("ඊළඟ", "next"),
    ("අඟහරුවාදා", "Tuesday"),
    ("රඟපෑම", "acting"),
    ("ගොඩනඟයි", "builds"),
    ("සඟල", "pair"),
]

#: Words that sound right today, spoken once each, unchanged, as a check that
#: the listeners and the run are sound. ගංගා and අම්බලම carry a full nasal.
REGRESSION_WORDS: list[tuple[str, str]] = [
    ("ගංගා", "river (Ganga)"),
    ("ලංකාව", "Lanka"),
    ("සිංහල", "Sinhala"),
    ("අම්බලම", "rest hall"),
    ("අනුරාධපුරය", "Anuradhapura"),
    ("පොත", "book"),
]

#: Every word is heard in the same sentence: a word alone is spoken less
#: stably than one inside speech. "X යන වචනය." = "the word X."
CARRIER = "{} යන වචනය."
SEEDS = (101, 202)

_PLACEHOLDER = "zq"  # survives the converter as plain ASCII; no Sinhala maps to it


@dataclass(frozen=True)
class Candidate:
    word: str
    gloss: str
    group: str  # "prenasal" or "regression"
    variant: str
    rationale: str
    ascii_word: str
    model_text: str


def ascii_word(word: str, nasal: str) -> str:
    """The word through the bundled converter, with ඟ's nasal part replaced.

    ඟ is swapped for a placeholder plus ග, so the converter handles the
    following vowel exactly as it does for ඟ; then the placeholder becomes
    ``nasal``. With ``nasal="n"`` this is today's spelling, which the tests
    check against the product's own ``to_model_input``.
    """
    marked = word.replace(SANYAKA_GA, _PLACEHOLDER.upper() + "ග")
    return sinhala_to_ascii(marked).replace(_PLACEHOLDER, nasal)


def in_carrier(ascii: str) -> str:
    """The carrier sentence's model text with this spelling for the word."""
    return sinhala_to_ascii(CARRIER.format("xwordx")).replace("xwordx", ascii)


def candidates() -> list[Candidate]:
    rows = []
    for word, gloss in PRENASAL_WORDS:
        for variant, (nasal, rationale) in VARIANTS.items():
            spelled = ascii_word(word, nasal)
            rows.append(
                Candidate(word, gloss, "prenasal", variant, rationale, spelled, in_carrier(spelled))
            )
    for word, gloss in REGRESSION_WORDS:
        spelled = sinhala_to_ascii(word)
        rows.append(
            Candidate(
                word,
                gloss,
                "regression",
                "current",
                "Sounds right today.",
                spelled,
                in_carrier(spelled),
            )
        )
    return rows


# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------


class Tokens:
    """XTTS's tokenizer for language "en", rebuilt from the bundle's vocab.json.

    Coqui's VoiceBpeTokenizer lowercases, collapses whitespace, prepends
    ``[en]`` and writes spaces as ``[SPACE]``. This repeats that so tokens can be
    checked without the TTS package. The GPU run records the real tokenizer's
    ids beside these, and they should agree.
    """

    def __init__(self, vocab: Path, config: Path) -> None:
        from tokenizers import Tokenizer

        self._tok = Tokenizer.from_file(str(vocab))
        self.unk = self._tok.token_to_id("[UNK]")
        self.limit = json.loads(config.read_text(encoding="utf-8"))["model_args"][
            "gpt_max_text_tokens"
        ]

    def encode(self, text: str) -> tuple[list[str], list[int]]:
        prepared = "[en]" + " ".join(text.lower().split()).replace(" ", "[SPACE]")
        encoding = self._tok.encode(prepared)
        return encoding.tokens, encoding.ids


def write_candidates(out: Path, tokens: Tokens) -> list[dict]:
    """``candidates.csv``, refusing any row with [UNK] or over the length limit."""
    rows, problems = [], []
    for candidate in candidates():
        word_tokens, word_ids = tokens.encode(candidate.ascii_word)
        _, ids = tokens.encode(candidate.model_text)
        unk = ids.count(tokens.unk)
        if unk or len(ids) > tokens.limit:
            problems.append(f"{candidate.word} {candidate.variant}: {unk} [UNK], {len(ids)} tokens")
        rows.append(
            {
                **asdict(candidate),
                "word_tokens": " ".join(word_tokens[1:]),
                "word_token_ids": " ".join(map(str, word_ids[1:])),
                "token_ids": " ".join(map(str, ids)),
                "token_count": len(ids),
                "token_limit": tokens.limit,
                "unk_count": unk,
            }
        )
    if problems:
        raise ValueError("candidates the model cannot read: " + "; ".join(problems))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# --------------------------------------------------------------------------
# the blind page
# --------------------------------------------------------------------------


def read_results(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_page(results_csv: Path, out: Path, *, seed: int = 0) -> Path:
    """A listening page in ``out/page/`` and its key in ``out/key.json``.

    The page and its clips can be handed to listeners: clip names are random,
    options are shuffled per question, and nothing on the page says which
    spelling made which clip. Keep ``key.json`` from them.
    """
    rows = read_results(results_csv)
    run = results_csv.parent
    rng = random.Random(seed)
    page = out / "page"
    clips = page / "clips"
    clips.mkdir(parents=True, exist_ok=True)

    key: dict[str, dict] = {}

    def clip(row: dict) -> str:
        name = secrets.token_hex(6) + ".wav"
        shutil.copyfile(run / row["output_path"], clips / name)
        key[name] = {k: row[k] for k in ("word", "group", "variant", "ascii_word", "seed")}
        return name

    questions = []
    prenasal = [r for r in rows if r["group"] == "prenasal"]
    for word, seed_value in sorted({(r["word"], r["seed"]) for r in prenasal}):
        options = [clip(r) for r in prenasal if r["word"] == word and r["seed"] == seed_value]
        rng.shuffle(options)
        questions.append({"kind": "choose", "word": word, "clips": options})
    for row in (r for r in rows if r["group"] == "regression" and r["seed"] == rows[0]["seed"]):
        questions.append({"kind": "check", "word": row["word"], "clips": [clip(row)]})
    rng.shuffle(questions)
    for number, question in enumerate(questions, start=1):
        question["id"] = f"q{number}"

    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    (page / "index.html").write_text(_html(questions), encoding="utf-8")
    return page / "index.html"


_CHOOSE = "වඩාත්ම නිවැරදි උච්චාරණය කුමක්ද? / Which says it most correctly?"
_CHECK = "මෙය නිවැරදිව උච්චාරණය කර තිබේද? / Is it said correctly?"
_NONE = "කිසිවක් නිවැරදි නැත / none is right"


def _radio(name: str, value: str, label: str) -> str:
    return f'<label><input type="radio" name="{name}" value="{value}"> {label}</label>'


def _audio(clip_name: str) -> str:
    return f'<audio controls preload="none" src="clips/{clip_name}"></audio>'


def _html(questions: list[dict]) -> str:
    letters = "ABCDEFGH"
    blocks = []
    for q in questions:
        name, clips = q["id"], q["clips"]
        if q["kind"] == "choose":
            rows = [
                f'<div class="opt">{_radio(name, c, letters[i])}{_audio(c)}</div>'
                for i, c in enumerate(clips)
            ]
            rows.append(f'<div class="opt">{_radio(name, "none:" + clips[0], _NONE)}</div>')
            question = _CHOOSE
        else:
            c = clips[0]
            yes, no = _radio(name, c + "|yes", "ඔව් / yes"), _radio(name, c + "|no", "නැත / no")
            rows = [f'<div class="opt">{_audio(c)}</div>', f'<div class="opt">{yes} {no}</div>']
            question = _CHECK
        legend = f'<span lang="si">{html.escape(q["word"])}</span> — {question}'
        body = "".join(rows)
        blocks.append(f'<fieldset id="{name}"><legend>{legend}</legend>{body}</fieldset>')
    page = _TEMPLATE.replace("{{QUESTIONS}}", "\n".join(blocks))
    return page.replace("{{COUNT}}", str(len(questions)))


_TEMPLATE = """<!doctype html>
<html lang="si"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>උච්චාරණ පරීක්ෂණය</title>
<style>
:root { --bg: #fbfaf7; --fg: #1d1b16; --muted: #5c574c; --line: #d9d3c4; --accent: #1f4e8c; }
@media (prefers-color-scheme: dark) { :root { --bg: #16150f; --fg: #f1ede2; --muted: #b9b2a2;
  --line: #3d3a31; --accent: #8db4ec; } }
body { background: var(--bg); color: var(--fg); font: 1.05rem/1.6 system-ui, "Noto Sans Sinhala",
  sans-serif; margin: 0 auto; max-width: 46rem; padding: 1rem; }
fieldset { border: 1px solid var(--line); border-radius: .6rem; margin: 0 0 1rem;
  padding: .8rem 1rem; }
legend { font-weight: 650; padding: 0 .3rem; }
.opt { align-items: center; display: flex; flex-wrap: wrap; gap: .6rem; margin: .4rem 0; }
audio { max-width: 100%; }
label { cursor: pointer; }
button { background: var(--accent); border: 0; border-radius: .5rem; color: var(--bg);
  font: inherit; padding: .6rem 1rem; }
.hint { color: var(--muted); }
</style></head><body>
<h1>උච්චාරණ පරීක්ෂණය / Pronunciation test</h1>
<p class="hint">එක් එක් ප්‍රශ්නයට සියලු හඬ පටිති අසා, වඩාත්ම නිවැරදි එක තෝරන්න. හඬ පටිති අහඹු ලෙස
පිළිවෙළ කර ඇත. / Listen to every clip, then pick the one that says the word most correctly.
The order is random. {{COUNT}} questions.</p>
<p><label>ඔබේ කේතය / Your code (no name): <input id="rater" autocomplete="off"></label></p>
<form id="test">
{{QUESTIONS}}
</form>
<p><button type="button" id="save">පිළිතුරු සුරකින්න / Save answers</button>
<span id="status" class="hint" role="status"></span></p>
<script>
document.getElementById("save").addEventListener("click", () => {
  const answers = {};
  for (const set of document.querySelectorAll("fieldset")) {
    const picked = set.querySelector("input:checked");
    if (picked) answers[set.id] = picked.value;
  }
  const rater = document.getElementById("rater").value.trim() || "anonymous";
  const body = JSON.stringify({ rater, answers }, null, 2);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([body], { type: "application/json" }));
  link.download = "answers-" + rater.replace(/[^\\w-]/g, "") + ".json";
  link.click();
  document.getElementById("status").textContent =
    Object.keys(answers).length + " / {{COUNT}} answered and saved.";
});
</script></body></html>
"""


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def score(key_path: Path, answer_paths: list[Path]) -> dict:
    """Aggregate choices: per word, how often each variant was preferred.

    Only counts leave this function. A spelling that wins here is a candidate
    for the override dictionary, not a fact about Sinhala: check agreement
    between listeners and between seeds before adopting it.
    """
    key = json.loads(key_path.read_text(encoding="utf-8"))
    chosen: dict[str, dict[str, int]] = {}
    regression: dict[str, dict[str, int]] = {}
    listeners = 0
    for path in answer_paths:
        listeners += 1
        answers = json.loads(path.read_text(encoding="utf-8"))["answers"]
        for value in answers.values():
            if "|" in value:
                clip_name, verdict = value.split("|", 1)
                word = key[clip_name]["word"]
                tally = regression.setdefault(word, {"yes": 0, "no": 0})
                tally[verdict] = tally.get(verdict, 0) + 1
            elif value.startswith("none:"):
                word = key[value.removeprefix("none:")]["word"]
                tally = chosen.setdefault(word, {})
                tally["none"] = tally.get("none", 0) + 1
            else:
                entry = key[value]
                tally = chosen.setdefault(entry["word"], {})
                tally[entry["variant"]] = tally.get(entry["variant"], 0) + 1
    overall: dict[str, int] = {}
    for tally in chosen.values():
        for variant, count in tally.items():
            overall[variant] = overall.get(variant, 0) + count
    return {
        "listeners": listeners,
        "preferred": chosen,
        "preferred_overall": overall,
        "regression": regression,
    }
