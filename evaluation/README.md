# Evaluation kit

This folder holds the measurements behind [`docs/product-plan.md`](../docs/product-plan.md) §11.1:
the protocol, the ethics templates, the rater rubric, the runners, and the aggregate results.

It measures the product's own code (the worker's pipeline, verifier and graph, and the API's
encoder), run from here. What is measured is therefore what ships.

## What is committed, and what never is

| Folder | Holds | In Git? |
| --- | --- | --- |
| `protocol.md`, `rubrics/`, `ethics/` | How each study is run, and the forms | Yes |
| `swara_eval/`, `tests/` | The runners and the statistics | Yes |
| `results/` | **Aggregates only**: counts, rates, intervals, percentiles | Yes |
| `data/` | Books, drafted questions, rating sheets, session logs, timings, audio | **Never** |

Two checks enforce this:

- `write_result` refuses a result with a per-person or per-item key, such as `participant`,
  `rater` or `item_id`.
- `scripts/verify-repo-hygiene.sh` fails the build if anything under `evaluation/data/` is
  tracked, or if `evaluation/results/` holds anything but aggregate JSON or Markdown.

Keep consent forms and anything that names a participant off this repository entirely,
wherever the approving institution says.

## Running it

From this folder, with the worker's and API's dependencies installed (see `services/*/README.md`),
and `langgraph` for RQ1:

```sh
python -m pytest                      # the kit's own tests
python -m swara_eval --help           # every command
```

| Step | Command | Needs |
| --- | --- | --- |
| RQ1: draft under three conditions | `python -m swara_eval rq1-run --book data/books/held-out.pdf` | `GEMINI_API_KEY`; the book split from any used in development |
| RQ1: rate | Give each teacher `data/rq1/sheet.csv`; keep `key.csv` from them | Two or more Sinhala subject teachers, with `rubrics/question-rubric.md` |
| RQ1: analyse | `python -m swara_eval rq1-analyse --ratings data/rq1/rater-a.csv data/rq1/rater-b.csv` | The completed sheets |
| Retrieval Recall@5 | `python -m swara_eval retrieval --questions data/questions.csv` | Held-out questions with gold pages |
| RQ3: summarise sessions | `python -m swara_eval rq3 --sessions data/rq3/sessions.csv --umux data/rq3/umux.csv` | Ethics approval and consent first |
| RQ4: first audio | `python -m swara_eval rq4-latency --base … --document … --segments … --label on-demand --device … --network … --server …` | A running API and a session token in `SWARA_EVAL_TOKEN` |
| RQ4: size per hour | `python -m swara_eval rq4-sizes --clips data/rq4/clips` | Real narration clips as WAV |
| RQ4: listening set | `python -m swara_eval rq4-pairs --clips data/rq4/clips` then `rq4-listening --sheets … --key …` | Native Sinhala listeners |

## The one switch that must never leave this folder

RQ1 needs questions made with the verifier or the blind check turned off. `draft_questions`
takes two private arguments for this, `_check` and `_blind`:

- No setting reaches them.
- No product code passes them; `tests/test_boundary.py` fails the build if any code under
  `services/` or `apps/` does.
- Questions made this way exist only in `data/` and on rating sheets. They never reach a reader.
