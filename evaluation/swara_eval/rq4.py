"""RQ4: does pre-rendering fix latency and cost, and what does Opus cost the voice?

* ``latency`` times first audio for a book's sentences against a running API,
  once before pre-rendering and once after, and reports p50 and p95.
* ``sizes`` encodes a folder of WAV clips as the API would, WAV and Opus, and
  reports bytes per audio hour.
* ``pairs`` builds a blind A/B listening set from the same clips, with the key
  kept apart; ``listening`` scores the completed sheet with an exact sign test.

The phone, network throttling and hardware are declared by whoever runs it and
recorded with the result; nothing here pretends to know them.
"""

from __future__ import annotations

import csv
import io
import json
import random
import time
import urllib.request
from pathlib import Path

import soundfile

from .stats import binomial_two_sided, percentile

SECONDS_PER_HOUR = 3600


def first_audio(base: str, token: str, document_id: str, segment_ids: list[str]) -> list[float]:
    """Seconds until each sentence's audio has fully arrived, in order."""
    timings = []
    for segment_id in segment_ids:
        request = urllib.request.Request(
            f"{base.rstrip('/')}/documents/{document_id}/segments/{segment_id}/audio",
            headers={"Authorization": f"Bearer {token}"},
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=600) as response:
            response.read()
        timings.append(time.perf_counter() - started)
    return timings


def latency_summary(timings: list[float], *, label: str, declared: dict[str, str]) -> dict:
    return {
        "condition": label,
        "sentences": len(timings),
        "p50_seconds": percentile(timings, 50),
        "p95_seconds": percentile(timings, 95),
        "declared": declared,
    }


def sizes(folder: Path) -> dict:
    """Bytes per hour of audio, WAV against Opus, over the same clips."""
    from sinhala_reader.audio import encode  # the product's own encoder

    seconds = 0.0
    totals = {"audio/wav": 0, "audio/ogg": 0}
    for path in sorted(folder.glob("*.wav")):
        samples, rate = soundfile.read(path, dtype="float32")
        seconds += len(samples) / rate
        for fmt in ("wav", "opus"):
            data, media_type = encode(samples, rate, fmt)
            totals[media_type] += len(data)
    if seconds == 0:
        raise ValueError(f"No WAV clips in {folder}.")
    per_hour = SECONDS_PER_HOUR / seconds
    return {
        "audio_seconds": round(seconds, 1),
        "megabytes_per_hour": {
            "wav": round(totals["audio/wav"] * per_hour / 1e6, 1),
            "opus": round(totals["audio/ogg"] * per_hour / 1e6, 1),
        },
    }


def pairs(folder: Path, out: Path, *, seed: int = 0) -> None:
    """Each clip as WAV and as decoded Opus, in a random order per pair.

    Opus is decoded back to WAV so a listener's player cannot give it away.
    """
    from sinhala_reader.audio import encode

    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    with (
        (out / "sheet.csv").open("w", newline="", encoding="utf-8-sig") as sheet,
        (out / "key.csv").open("w", newline="", encoding="utf-8") as key,
    ):
        rows, keys = csv.writer(sheet), csv.writer(key)
        rows.writerow(["pair", "a", "b", "preferred (a, b or same)"])
        keys.writerow(["pair", "opus_is"])
        for number, path in enumerate(sorted(folder.glob("*.wav")), start=1):
            samples, rate = soundfile.read(path, dtype="float32")
            data, media_type = encode(samples, rate, "opus")
            if media_type != "audio/ogg":
                continue
            decoded, decoded_rate = soundfile.read(io.BytesIO(data), dtype="float32")
            opus_first = rng.random() < 0.5
            names = (f"{number:03d}-a.wav", f"{number:03d}-b.wav")
            original, compressed = (samples, rate), (decoded, decoded_rate)
            first, second = (compressed, original) if opus_first else (original, compressed)
            soundfile.write(out / names[0], *first)
            soundfile.write(out / names[1], *second)
            rows.writerow([number, names[0], names[1], ""])
            keys.writerow([number, "a" if opus_first else "b"])


def listening(sheets: list[Path], key: Path) -> dict:
    """How often listeners preferred WAV, Opus, or heard no difference."""
    with key.open(encoding="utf-8") as handle:
        opus_is = {row["pair"]: row["opus_is"] for row in csv.DictReader(handle)}
    wav = opus = same = 0
    for sheet in sheets:
        with sheet.open(encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                choice = (row.get("preferred (a, b or same)") or "").strip().lower()
                if choice == "same":
                    same += 1
                elif choice in ("a", "b"):
                    if choice == opus_is[row["pair"]]:
                        opus += 1
                    else:
                        wav += 1
    return {
        "preferred_wav": wav,
        "preferred_opus": opus,
        "no_difference": same,
        "sign_test_p": binomial_two_sided(wav, wav + opus),
        "listeners": len(sheets),
    }


def save_timings(path: Path, timings: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(timings))
