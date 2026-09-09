"""Generate real audio from the Sinhala XTTS checkpoint and check it.

This is the first thing in the project that actually loads the model. Everything
else so far reasons about text; this proves the checkpoint loads, the documented
procedure is right, and the normalised text produces audible speech.

It does **not** run in CI. It needs the 5.6 GB checkpoint and the heavy inference
stack, neither of which belongs on a pull-request runner, and CLAUDE.md requires
real-model checks to run on trusted, access-controlled hardware and to be
reported separately from fast pull-request checks.

Usage
-----
Point it at an environment that has torch, coqui-tts, and soundfile installed,
and at the model bundle::

    SINHALA_TTS_MODEL_DIR=/path/to/xtts_si_female \\
    PYTHONPATH=src python scripts/smoke_synthesize.py --out ../../data/generated/smoke

Options::

    --cases plain-short,year   only these regression cases
    --device cpu|cuda          override automatic selection
    --precision fp16|fp32      GPU only; fp16 is what fits a small card
    --no-audio                 report timings and checks without writing WAVs

What it reports
---------------
Load time, per-case synthesis time, real-time factor, the device actually used,
and the audio checks from :mod:`sinhala_tts.audio_checks`. A non-zero exit means
at least one case failed a check — which is a signal to listen, not a
measurement of quality. **Nothing here judges intelligibility or pronunciation.
Only listening does that**, which is why the WAVs are written out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from sinhala_tts.audio_checks import EXPECTED_SAMPLE_RATE, check_audio  # noqa: E402
from sinhala_tts.normalize import (  # noqa: E402
    NORMALIZER_VERSION,
    is_speakable,
    to_model_input,
    to_speech_text,
)
from sinhala_tts.regression_sentences import CASES, case_by_id  # noqa: E402

# Confirmed from the config, the front end's own self-test, and the owner's
# working service. The config's `languages` list is XTTS's stock 17 and does not
# contain "si"; reading a token out of it would silently select Hindi.
LANGUAGE_TOKEN = "en"

# The working service overrides the config's 0.75 deliberately: a book reader
# wants consistency between sentences more than expressive variation.
TEMPERATURE = 0.65

CONDITIONING_SAMPLE_RATE = 22050

REQUIRED_FILES = ("config.json", "model.pth", "vocab.json", "reference.wav")


def resolve_model_dir(explicit: str | None) -> Path:
    candidate = explicit or os.environ.get("SINHALA_TTS_MODEL_DIR")
    if not candidate:
        # The workspace default, which exists only on a machine that has been
        # given the bundle out of band.
        candidate = str(Path(__file__).resolve().parents[3] / "models" / "xtts_si_female")
    path = Path(candidate).expanduser().resolve()
    missing = [name for name in REQUIRED_FILES if not (path / name).is_file()]
    if missing:
        raise SystemExit(
            f"Model bundle at {path} is missing: {', '.join(missing)}.\n"
            "The checkpoint is delivered out of band and is never in Git. Set "
            "SINHALA_TTS_MODEL_DIR to its location."
        )
    return path


def load_model(model_dir: Path, device: str | None, precision: str):
    """Load once, exactly as documented in docs/model-inference-manifest.md."""
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    config = XttsConfig()
    config.load_json(str(model_dir / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(
        config,
        checkpoint_path=str(model_dir / "model.pth"),
        vocab_path=str(model_dir / "vocab.json"),
        use_deepspeed=False,
    )
    model.eval()

    chosen = device or ("cuda" if torch.cuda.is_available() else "cpu")
    half = False
    if chosen == "cuda":
        try:
            model.cuda()
            if precision == "fp16":
                model.half()
                half = True
        except torch.cuda.OutOfMemoryError:
            # Reported, never silent. CLAUDE.md forbids quietly moving
            # overloaded inference to CPU; the agreed position is to keep the
            # fallback but make it visible, so this prints and is recorded in
            # the report rather than being logged and forgotten.
            print("  WARNING: model does not fit in VRAM; falling back to CPU", flush=True)
            torch.cuda.empty_cache()
            model.float().cpu()
            chosen = "cpu"
    return model, config, chosen, half


def conditioning(model, config, model_dir: Path):
    """Speaker latents from reference.wav, computed once.

    Read with soundfile rather than through get_conditioning_latents(audio_path=),
    which from torch 2.9 routes audio IO through torchcodec and needs FFmpeg's
    native libraries installed system-wide.
    """
    import soundfile as sf
    import torch

    wav, rate = sf.read(str(model_dir / "reference.wav"), dtype="float32", always_2d=True)
    audio = torch.from_numpy(wav.mean(axis=1)).unsqueeze(0)

    if rate != CONDITIONING_SAMPLE_RATE:
        import torchaudio

        audio = torchaudio.functional.resample(audio, rate, CONDITIONING_SAMPLE_RATE)
        rate = CONDITIONING_SAMPLE_RATE

    # Must match the model's device *and* dtype: a float32 reference against a
    # half-precision model fails deep inside the GPT forward pass with an error
    # naming neither dtype nor this function.
    parameter = next(model.parameters())
    audio = audio.to(device=parameter.device, dtype=parameter.dtype)

    gpt_cond_latent = model.get_gpt_cond_latents(
        audio,
        rate,
        length=getattr(config, "gpt_cond_len", 30),
        chunk_length=getattr(config, "gpt_cond_chunk_len", 4),
    )
    speaker_embedding = model.get_speaker_embedding(audio, rate)
    return gpt_cond_latent, speaker_embedding


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir")
    parser.add_argument("--out", default="smoke-output")
    parser.add_argument("--cases", help="comma-separated case ids; default is all")
    parser.add_argument("--device", choices=["cpu", "cuda"])
    parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "synthesise each case this many times. Generation is stochastic, so "
            "duration varies between runs for identical input; repeats are how "
            "that spread is measured rather than guessed at"
        ),
    )
    args = parser.parse_args()

    cases = (
        tuple(case_by_id(name.strip()) for name in args.cases.split(",")) if args.cases else CASES
    )

    model_dir = resolve_model_dir(args.model_dir)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import soundfile as sf
    import torch

    print(f"model bundle : {model_dir}")
    print(f"output       : {out_dir}")
    print(f"torch        : {torch.__version__}  cuda_available={torch.cuda.is_available()}")
    print(f"normalizer   : v{NORMALIZER_VERSION}")
    print(f"language     : {LANGUAGE_TOKEN!r}  temperature={TEMPERATURE}")
    print()

    print("loading model...", flush=True)
    started = time.perf_counter()
    model, config, device, half = load_model(model_dir, args.device, args.precision)
    load_seconds = time.perf_counter() - started
    print(f"  loaded in {load_seconds:.1f}s on {device}" + (" (fp16)" if half else ""))

    started = time.perf_counter()
    gpt_cond_latent, speaker_embedding = conditioning(model, config, model_dir)
    conditioning_seconds = time.perf_counter() - started
    print(f"  speaker conditioning in {conditioning_seconds:.1f}s")
    print()

    results = []
    failures = 0

    for case in cases:
        spoken = to_speech_text(case.text)
        model_text = to_model_input(case.text)

        print(f"[{case.case_id}]")
        print(f"  display : {case.text!r}")
        print(f"  spoken  : {spoken!r}")
        print(f"  model   : {model_text!r}")

        if not is_speakable(model_text):
            print("  SKIPPED: normalises to nothing speakable")
            results.append({"case_id": case.case_id, "skipped": "not speakable"})
            failures += 1
            continue

        runs = []
        for attempt in range(1, args.repeat + 1):
            started = time.perf_counter()
            with torch.inference_mode():
                out = model.inference(
                    model_text,
                    LANGUAGE_TOKEN,
                    gpt_cond_latent,
                    speaker_embedding,
                    speed=1.0,
                    temperature=TEMPERATURE,
                )
            synthesis_seconds = time.perf_counter() - started

            wav = out["wav"]
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().to(device="cpu", dtype=torch.float32).numpy()
            samples = np.asarray(wav, dtype=np.float32)

            report = check_audio(samples, EXPECTED_SAMPLE_RATE, model_text=model_text)
            real_time_factor = (
                synthesis_seconds / report.duration_seconds
                if report.duration_seconds
                else float("inf")
            )

            label = f"  run {attempt}: " if args.repeat > 1 else "  "
            print(f"{label}{report.summary()}")
            print(f"  synthesis {synthesis_seconds:.1f}s, real-time factor {real_time_factor:.2f}x")
            for problem in report.problems:
                print(f"  PROBLEM: {problem}")
            if not report.ok:
                failures += 1

            if not args.no_audio:
                suffix = f"-{attempt}" if args.repeat > 1 else ""
                destination = out_dir / f"{case.case_id}{suffix}.wav"
                sf.write(
                    destination,
                    np.clip(samples, -1.0, 1.0),
                    EXPECTED_SAMPLE_RATE,
                    format="WAV",
                    subtype="PCM_16",
                )
                print(f"  wrote {destination.name}")

            runs.append(
                {
                    "attempt": attempt,
                    "synthesis_seconds": round(synthesis_seconds, 3),
                    "real_time_factor": round(real_time_factor, 3),
                    "audio": asdict(report),
                }
            )

        durations = [run["audio"]["duration_seconds"] for run in runs]
        if args.repeat > 1:
            spread = max(durations) / min(durations) if min(durations) else float("inf")
            print(
                f"  duration across {args.repeat} runs: "
                f"min {min(durations):.2f}s, max {max(durations):.2f}s, "
                f"spread {spread:.2f}x"
            )

        results.append(
            {
                "case_id": case.case_id,
                "why": case.why,
                "display_text": case.text,
                "spoken_text": spoken,
                "model_text": model_text,
                "runs": runs,
                "duration_min": round(min(durations), 3),
                "duration_max": round(max(durations), 3),
            }
        )
        print()

    summary = {
        "model_dir": str(model_dir),
        "device": device,
        "half_precision": half,
        "torch_version": torch.__version__,
        "language_token": LANGUAGE_TOKEN,
        "temperature": TEMPERATURE,
        "normalizer_version": NORMALIZER_VERSION,
        "load_seconds": round(load_seconds, 2),
        "conditioning_seconds": round(conditioning_seconds, 2),
        "cases": results,
        "failures": failures,
    }
    report_path = out_dir / "smoke-report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(cases) - failures}/{len(cases)} cases passed automated checks")
    print(f"report: {report_path}")
    print()
    print("Automated checks cannot tell you whether the speech is intelligible or")
    print("correctly pronounced. Listen to the WAVs before trusting any of this.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
