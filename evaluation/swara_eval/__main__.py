"""``python -m swara_eval <command>``: each step of the protocol, one command.

Raw material is written under ``evaluation/data/`` (ignored by Git); the
aggregate a command ends with is written under ``evaluation/results/``.
See ``evaluation/README.md`` for the order to run them in.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import rq3, rq4
from .results import DATA, write_result


def _rq1_run(args: argparse.Namespace) -> None:
    from sinhala_documents.quiz_graph import gemini_transport

    from .books import prepare, source_passages
    from .rq1 import CONDITIONS, rating_sheet, run_condition, save_run

    passages = source_passages(prepare(Path(args.book)))
    transport = gemini_transport()
    drafted, costs = [], []
    for condition in CONDITIONS:
        made, cost = run_condition(condition, passages, transport, target=args.target)
        drafted += made
        costs.append(cost)
        print(f"{condition}: {cost.kept} questions, {cost.calls} model calls")
    out = Path(args.out)
    save_run(out, drafted, costs)
    rating_sheet(out, drafted, passages, seed=args.seed)
    print(f"Rating sheet: {out / 'sheet.csv'}. Keep {out / 'key.csv'} from the raters.")


def _rq1_analyse(args: argparse.Namespace) -> None:
    from .rq1 import RunCost, analyse, read_ratings

    run = Path(args.run)
    costs = [RunCost(**c) for c in json.loads((run / "costs.json").read_text())]
    ratings = read_ratings([Path(p) for p in args.ratings])
    print(write_result(args.name, {"rq": "RQ1", **analyse(run / "key.csv", ratings, costs)}))


def _retrieval(args: argparse.Namespace) -> None:
    from .retrieval import compare_modes, read_questions, recall_at

    questions = read_questions(Path(args.questions))
    if args.compare:
        payload = {"rq": "retrieval", "modes": compare_modes(questions, DATA, k=args.k)}
    else:
        payload = {
            "rq": "retrieval",
            **recall_at(questions, DATA, k=args.k, mode=args.mode),
        }
    print(write_result(args.name, payload))


def _answers(args: argparse.Namespace) -> None:
    from .answers import evaluate, read_answer_questions

    questions = read_answer_questions(Path(args.questions))
    print(
        write_result(
            args.name,
            {"rq": "answers", **evaluate(questions, DATA, mode=args.mode)},
        )
    )


def _rq3(args: argparse.Namespace) -> None:
    umux = Path(args.umux) if args.umux else None
    print(write_result(args.name, {"rq": "RQ3", **rq3.summarise(Path(args.sessions), umux)}))


def _rq4_latency(args: argparse.Namespace) -> None:
    token = os.environ[args.token_env]
    segments = Path(args.segments).read_text(encoding="utf-8").split()
    timings = rq4.first_audio(args.base, token, args.document, segments)
    rq4.save_timings(DATA / "rq4" / f"timings-{args.label}.json", timings)
    declared = {"device": args.device, "network": args.network, "server": args.server}
    summary = rq4.latency_summary(timings, label=args.label, declared=declared)
    print(write_result(f"{args.name}-{args.label}", {"rq": "RQ4", **summary}))


def _rq4_sizes(args: argparse.Namespace) -> None:
    print(write_result(args.name, {"rq": "RQ4", **rq4.sizes(Path(args.clips))}))


def _rq4_pairs(args: argparse.Namespace) -> None:
    rq4.pairs(Path(args.clips), Path(args.out), seed=args.seed)
    print(f"Listening set in {args.out}; keep key.csv from the listeners.")


def _rq4_listening(args: argparse.Namespace) -> None:
    result = rq4.listening([Path(p) for p in args.sheets], Path(args.key))
    print(write_result(args.name, {"rq": "RQ4", **result}))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="swara_eval", description=__doc__)
    commands = parser.add_subparsers(required=True)

    c = commands.add_parser("rq1-run", help="Draft questions under the three conditions.")
    c.add_argument("--book", required=True, help="A held-out book under evaluation/data/.")
    c.add_argument("--out", default=str(DATA / "rq1"))
    c.add_argument("--target", type=int, default=5)
    c.add_argument("--seed", type=int, default=0)
    c.set_defaults(run=_rq1_run)

    c = commands.add_parser("rq1-analyse", help="Score the raters' sheets against the key.")
    c.add_argument("--run", default=str(DATA / "rq1"))
    c.add_argument("--ratings", nargs="+", required=True)
    c.add_argument("--name", default="rq1")
    c.set_defaults(run=_rq1_analyse)

    c = commands.add_parser("retrieval", help="Recall@k over a question file.")
    c.add_argument("--questions", required=True)
    c.add_argument("--k", type=int, default=5)
    c.add_argument("--mode", default="lexical", choices=("lexical", "dense", "hybrid"))
    c.add_argument("--compare", action="store_true", help="Score lexical, dense and hybrid.")
    c.add_argument("--name", default="retrieval")
    c.set_defaults(run=_retrieval)

    c = commands.add_parser("answers", help="Citation, correctness and abstention on answers.")
    c.add_argument("--questions", required=True)
    c.add_argument("--mode", default="lexical", choices=("lexical", "dense", "hybrid"))
    c.add_argument("--name", default="answers")
    c.set_defaults(run=_answers)

    c = commands.add_parser("rq3", help="Summarise task sessions and UMUX-Lite.")
    c.add_argument("--sessions", required=True)
    c.add_argument("--umux")
    c.add_argument("--name", default="rq3")
    c.set_defaults(run=_rq3)

    c = commands.add_parser("rq4-latency", help="Time first audio against a running API.")
    c.add_argument("--base", required=True)
    c.add_argument("--token-env", default="SWARA_EVAL_TOKEN")
    c.add_argument("--document", required=True)
    c.add_argument("--segments", required=True, help="A file of segment ids, one per line.")
    c.add_argument("--label", required=True, help="on-demand or pre-rendered")
    c.add_argument("--device", required=True)
    c.add_argument("--network", required=True)
    c.add_argument("--server", required=True)
    c.add_argument("--name", default="rq4-latency")
    c.set_defaults(run=_rq4_latency)

    c = commands.add_parser("rq4-sizes", help="Megabytes per audio hour, WAV against Opus.")
    c.add_argument("--clips", required=True)
    c.add_argument("--name", default="rq4-sizes")
    c.set_defaults(run=_rq4_sizes)

    c = commands.add_parser("rq4-pairs", help="Build a blind WAV/Opus listening set.")
    c.add_argument("--clips", required=True)
    c.add_argument("--out", default=str(DATA / "rq4" / "listening"))
    c.add_argument("--seed", type=int, default=0)
    c.set_defaults(run=_rq4_pairs)

    c = commands.add_parser("rq4-listening", help="Score the listeners' sheets.")
    c.add_argument("--sheets", nargs="+", required=True)
    c.add_argument("--key", required=True)
    c.add_argument("--name", default="rq4-listening")
    c.set_defaults(run=_rq4_listening)

    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
