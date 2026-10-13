"""Speak the pronunciation candidates on a GPU. Inference only; costs money.

    modal run evaluation/pronunciation_modal.py \\
        --candidates evaluation/data/pronunciation/candidates.csv \\
        --out evaluation/data/pronunciation --reference female --confirm

Without ``--confirm`` it only says what it would do and spends nothing.

A separate, temporary Modal app (``modal run``), never the deployed voice. It
uses the deployed voice's image, volume and checkpoint read-only, so the
runtime is the same one readers hear, and it changes neither.

Held constant across every candidate, so the spelling is the only difference:

- **one reference clip** (``--reference``), conditioned once;
- **the product's decoding settings** (``SynthesisSettings()``), recorded;
- **the same seeds** for every candidate of a word: Python, NumPy and torch
  are seeded before each clip.

Every row is tokenised by the model's real tokenizer first. Any [UNK] or a
sequence over the model's limit stops the run before audio is made.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import wave
from datetime import UTC, datetime
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "tts" / "deploy"), str(ROOT / "services" / "tts" / "src")]

from modal_app import GPU, MODEL_DIR, MODEL_MOUNT, PRECISION, image, volume  # noqa: E402

app = modal.App("swara-pronunciation-test")

#: Reference clips on the voice's volume. "female-original" is the clip the
#: product used before 2026-10-13, kept in /backup.
REFERENCES = {
    "female": f"{MODEL_DIR}/reference.wav",
    "male": f"{MODEL_DIR}/reference_male.wav",
    "female-original": f"{MODEL_MOUNT}/backup/reference.original-fa1e2295.wav",
}

#: Measured on an A10G for sentences of this length (about 3 s each), plus a
#: cold start. Printed before anything runs; not a promise.
SECONDS_PER_CLIP = 3.0


@app.function(image=image, gpu=GPU, volumes={MODEL_MOUNT: volume}, timeout=60 * 60)
def speak(rows: list[dict], seeds: list[int], reference: str) -> dict:
    import hashlib
    import random

    import numpy as np
    import torch
    from sinhala_tts.adapter import SynthesisSettings, XttsAdapter
    from sinhala_tts.audio_checks import check_audio

    adapter = XttsAdapter(MODEL_DIR, device="cuda", precision=PRECISION, max_concurrent=1)
    adapter.load()
    loaded = adapter._loaded  # noqa: SLF001 - the experiment drives the loaded model directly
    clip = Path(REFERENCES[reference])
    conditioning = XttsAdapter._compute_conditioning(loaded.model, loaded.config, clip)  # noqa: SLF001
    settings = SynthesisSettings()

    tokenizer = loaded.model.tokenizer
    unk = tokenizer.tokenizer.token_to_id("[UNK]")
    limit = loaded.config.model_args.gpt_max_text_tokens
    real_ids = {}
    for row in rows:
        ids = tokenizer.encode(row["model_text"], settings.language)
        if unk in ids or len(ids) > limit:
            raise ValueError(f"{row['word']} {row['variant']}: [UNK] or over {limit} tokens")
        real_ids[row["model_text"]] = ids

    rate = int(getattr(loaded.config.model_args, "output_sample_rate", 24000))
    spoken = []
    for row in rows:
        for seed in seeds:
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            with torch.inference_mode():
                out = loaded.model.inference(
                    row["model_text"],
                    settings.language,
                    *conditioning,
                    speed=settings.speed,
                    temperature=settings.temperature,
                    repetition_penalty=settings.repetition_penalty,
                    top_k=settings.top_k,
                    top_p=settings.top_p,
                    length_penalty=settings.length_penalty,
                    do_sample=settings.do_sample,
                )
            wav = out["wav"]
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().to("cpu", torch.float32).numpy()
            samples = np.asarray(wav, dtype=np.float32)
            report = check_audio(samples, rate, model_text=row["model_text"])
            spoken.append(
                {
                    "row": row,
                    "seed": seed,
                    "real_token_ids": " ".join(map(str, real_ids[row["model_text"]])),
                    "wav": _to_wav(samples, rate),
                    "duration_seconds": round(len(samples) / rate, 3),
                    "audio_problems": "; ".join(report.problems),
                }
            )
    return {
        "clips": spoken,
        "model_version": loaded.version,
        "reference": reference,
        "reference_sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
        "settings": vars(settings),
        "precision": PRECISION,
        "gpu": GPU,
    }


def _to_wav(samples, rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


@app.local_entrypoint()
def main(
    candidates: str,
    out: str,
    reference: str = "female",
    seeds: str = "101,202",
    confirm: bool = False,
) -> None:
    if reference not in REFERENCES:
        raise SystemExit(f"--reference must be one of {', '.join(REFERENCES)}")
    with open(candidates, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    seed_list = [int(s) for s in seeds.split(",")]
    clips = len(rows) * len(seed_list)
    minutes = clips * SECONDS_PER_CLIP / 60 + 1.5
    print(f"{len(rows)} candidates x {len(seed_list)} seeds = {clips} clips, reference {reference}")
    print(f"About {minutes:.0f} minutes on one {GPU}, cold start included.")
    if not confirm:
        print("Dry run: nothing was sent. Add --confirm to spend the GPU time.")
        return

    result = speak.remote(rows, seed_list, reference)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = Path(out) / f"run-{stamp}-{reference}"
    (run / "audio").mkdir(parents=True)
    fields = [
        "word",
        "gloss",
        "group",
        "variant",
        "ascii_word",
        "model_text",
        "token_ids",
        "real_token_ids",
        "tokens_match",
        "seed",
        "reference",
        "output_path",
        "duration_seconds",
        "audio_problems",
        "model_version",
    ]
    with (run / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for number, clip in enumerate(result["clips"]):
            row = clip["row"]
            path = Path("audio") / f"{number:03d}.wav"
            (run / path).write_bytes(clip["wav"])
            writer.writerow(
                {
                    **{
                        k: row[k]
                        for k in (
                            "word",
                            "gloss",
                            "group",
                            "variant",
                            "ascii_word",
                            "model_text",
                            "token_ids",
                        )
                    },
                    "real_token_ids": clip["real_token_ids"],
                    "tokens_match": clip["real_token_ids"] == row["token_ids"],
                    "seed": clip["seed"],
                    "reference": result["reference"],
                    "output_path": path.as_posix(),
                    "duration_seconds": clip["duration_seconds"],
                    "audio_problems": clip["audio_problems"],
                    "model_version": result["model_version"],
                }
            )
    meta = {k: v for k, v in result.items() if k != "clips"}
    (run / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {len(result['clips'])} clips and results.csv to {run}")
