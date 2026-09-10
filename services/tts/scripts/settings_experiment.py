"""Does changing generation settings stop the model appending audio?

The model sometimes keeps generating after a sentence ends — confirmed by
listening, measured by :mod:`sinhala_tts.speech_regions`. Before building retry
logic around that, it is worth finding out whether it can be prevented at the
source.

This synthesises one fixed sentence many times under several settings and
reports, per configuration, how often the output was clean. Generation is
stochastic, so a single run per configuration would measure noise; repeats are
the whole point.

Like the smoke test, this needs the checkpoint and does not run in CI.

Usage
-----
::

    SINHALA_TTS_MODEL_DIR=/path/to/xtts_si_female \\
    PYTHONPATH=src python scripts/settings_experiment.py --repeat 4

What it cannot tell you
-----------------------
Whether the audio still sounds good. A setting that reliably stops the model
early might also make it flat, clipped, or unintelligible. **Every configuration
that looks promising here must be listened to before it is adopted**, which is
why the WAVs are kept.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from smoke_synthesize import (  # noqa: E402
    LANGUAGE_TOKEN,
    conditioning,
    load_model,
    resolve_model_dir,
)

from sinhala_tts.audio_checks import EXPECTED_SAMPLE_RATE, check_audio  # noqa: E402
from sinhala_tts.normalize import to_model_input  # noqa: E402
from sinhala_tts.regression_sentences import case_by_id  # noqa: E402

# The settings actually in effect today. Note repetition_penalty: the caller
# does not pass it, so Xtts.inference's own default of 10.0 applies, NOT the
# 5.0 in config.json. Everything here is measured against that reality.
BASELINE = {
    "temperature": 0.65,
    "length_penalty": 1.0,
    "repetition_penalty": 10.0,
    "top_k": 50,
    "top_p": 0.85,
    "do_sample": True,
}

# Each variation changes one thing from the baseline, so a difference can be
# attributed. The hypothesis in every case is about the stop token: the model
# is failing to end the sequence, and more conservative decoding might make it
# end reliably.
VARIATIONS: dict[str, dict[str, object]] = {
    "baseline": {},
    # Less room to wander off the end of the sentence.
    "low-temperature": {"temperature": 0.30},
    # Narrower sampling, same reasoning by a different route.
    "narrow-sampling": {"top_k": 20, "top_p": 0.60},
    # Below 1.0 favours shorter sequences, which is what we want.
    "short-length-penalty": {"length_penalty": 0.5},
    # The value config.json specifies but the caller never passes. Worth knowing
    # whether the documented setting is better or worse than the one in use.
    "config-repetition-penalty": {"repetition_penalty": 5.0},
    # No sampling at all. Removes the run-to-run variance entirely; the question
    # is what it costs in naturalness, which only listening answers.
    "greedy": {"do_sample": False},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir")
    parser.add_argument("--out", default="settings-experiment")
    parser.add_argument("--case", default="plain-short")
    parser.add_argument("--repeat", type=int, default=4)
    parser.add_argument("--device", choices=["cpu", "cuda"])
    parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")
    parser.add_argument("--only", help="comma-separated variation names")
    args = parser.parse_args()

    case = case_by_id(args.case)
    model_text = to_model_input(case.text)

    variations = VARIATIONS
    if args.only:
        wanted = {name.strip() for name in args.only.split(",")}
        variations = {k: v for k, v in VARIATIONS.items() if k in wanted}

    model_dir = resolve_model_dir(args.model_dir)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import soundfile as sf
    import torch

    print(f"case      : {case.case_id}")
    print(f"display   : {case.text!r}")
    print(f"model text: {model_text!r}")
    print(f"repeats   : {args.repeat} per variation")
    print()

    print("loading model...", flush=True)
    model, config, device, half = load_model(model_dir, args.device, args.precision)
    gpt_cond_latent, speaker_embedding = conditioning(model, config, model_dir)
    print(f"  ready on {device}\n")

    results = {}
    for name, override in variations.items():
        settings = {**BASELINE, **override}
        print(f"[{name}] {override or 'unchanged'}")

        durations: list[float] = []
        trailing: list[float] = []
        clean = 0

        for attempt in range(1, args.repeat + 1):
            started = time.perf_counter()
            with torch.inference_mode():
                out = model.inference(
                    model_text,
                    LANGUAGE_TOKEN,
                    gpt_cond_latent,
                    speaker_embedding,
                    speed=1.0,
                    **settings,
                )
            elapsed = time.perf_counter() - started

            wav = out["wav"]
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().to(device="cpu", dtype=torch.float32).numpy()
            samples = np.asarray(wav, dtype=np.float32)

            report = check_audio(
                samples,
                EXPECTED_SAMPLE_RATE,
                model_text=model_text,
            )
            durations.append(report.duration_seconds)
            trailing.append(report.trailing_audio_seconds)
            if report.trailing_audio_seconds == 0:
                clean += 1

            flag = "clean" if report.trailing_audio_seconds == 0 else "APPENDED"
            print(
                f"  run {attempt}: {report.duration_seconds:5.2f}s  "
                f"appended {report.trailing_audio_seconds:5.2f}s  "
                f"regions {report.speech_regions}  {flag}  ({elapsed:.0f}s)"
            )

            sf.write(
                out_dir / f"{name}-{attempt}.wav",
                np.clip(samples, -1.0, 1.0),
                EXPECTED_SAMPLE_RATE,
                format="WAV",
                subtype="PCM_16",
            )

        results[name] = {
            "settings": settings,
            "clean_runs": clean,
            "total_runs": args.repeat,
            "durations": [round(d, 3) for d in durations],
            "trailing": [round(t, 3) for t in trailing],
            "median_duration": round(statistics.median(durations), 3),
            "mean_trailing": round(statistics.fmean(trailing), 3),
        }
        print(
            f"  => {clean}/{args.repeat} clean, "
            f"median duration {statistics.median(durations):.2f}s, "
            f"mean appended {statistics.fmean(trailing):.2f}s\n"
        )

    print(f"{'variation':28} {'clean':>7} {'median dur':>11} {'mean appended':>14}")
    print("-" * 64)
    for name, r in results.items():
        print(
            f"{name:28} {r['clean_runs']}/{r['total_runs']:>5} "
            f"{r['median_duration']:>10.2f}s {r['mean_trailing']:>13.2f}s"
        )

    report_path = out_dir / "settings-experiment.json"
    report_path.write_text(
        json.dumps(
            {
                "case_id": case.case_id,
                "model_text": model_text,
                "device": device,
                "half_precision": half,
                "repeat": args.repeat,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nreport: {report_path}")
    print("\nA clean rate is not a quality judgement. Listen before adopting anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
