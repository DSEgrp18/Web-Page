# services/tts

The Sinhala XTTS text front end, and eventually the inference adapter.

Right now this package contains **only the text path**. Model loading and
synthesis are not implemented yet. That order is deliberate: the text front end
is where this model is most easily broken, it is pure standard library, and it
can be tested exhaustively without a GPU or the 5.6 GB checkpoint — so it is the
part worth getting right and locking down first.

See [`docs/model-inference-manifest.md`](../../docs/model-inference-manifest.md)
for the verified inference procedure, settings, limits, and dependencies.

## Why the text front end matters this much

XTTS-v2's tokenizer is a whitespace-pretokenised BPE with an `[UNK]` fallback,
and the Sinhala block is absent from its vocabulary. One Sinhala codepoint turns
the **whole word** into `[UNK]`. The fine-tune works by romanising Sinhala into
ASCII the base model already knows and training under the English language
token.

So `to_ascii()` is not a nicety. Skipping it does not produce worse audio; it
produces confident-sounding babble. The vendored front end must match training
exactly, which is why CI verifies its hash and lint never touches it.

## Running the checks

From this directory, with Python 3.12 or newer:

```bash
python -m pip install "pytest>=8" "ruff>=0.15"
python -m pytest
ruff check .
ruff format --check .
```

No install step is needed: `pyproject.toml` puts `src` on the test path
directly. On Windows, set `PYTHONIOENCODING=utf-8` first or the console cannot
print Sinhala test output.

## Layout

```text
src/sinhala_tts/vendor/    The training front end, vendored unchanged. Do not edit.
src/sinhala_tts/           Normaliser, number expansion, audio checks, regression set.
scripts/                   Real-model smoke test. Needs the checkpoint; not run in CI.
tests/                     Characterisation, integrity, and unit tests. Run in CI.
```

## The adapter

`sinhala_tts.adapter` is the boundary the rest of the application talks to:

```python
result = adapter.synthesize(text, voice_id, settings, document_version="v1")
result.samples          # float32 waveform
result.metadata         # what produced it, and its cache key
```

Everything above this line deals in text and audio segments. It never imports
torch, never knows where the checkpoint lives, and never needs a GPU to be
tested.

| Implementation | Needs | Output |
| --- | --- | --- |
| `XttsAdapter` | The bundle and the inference stack | Real speech |
| `DevelopmentAdapter` | Nothing | **A placeholder tone, not speech** |

### The development adapter is not a voice

It exists so the reader, the API, and the job pipeline can be built and tested
without the 5.6 GB bundle. Its output is a 440 Hz tone — deliberately not
something that could pass a casual listen and reach a demo.

Every result it produces carries `is_real_model=False` and a `development-`
voice id, and that flag is part of the cache key, so a placeholder can never be
served from cache in place of narration. It applies the same text validation as
the real adapter, so a segment rejected in production is rejected here too.

### What each segment records

CLAUDE.md requires the model version and synthesis settings on every generated
segment, and requires cache identity to cover the text hash, document version,
model version, normalizer version, voice, and generation settings. Both are in
`SynthesisMetadata`, so cached audio can be traced to exactly what made it — and
bumping `NORMALIZER_VERSION` invalidates audio whose speech would now differ.

### Readiness is not liveness

`ReadinessState` separates `NOT_LOADED`, `LOADING`, `READY`, `DEGRADED` and
`FAILED`. `DEGRADED` means serving on CPU after the GPU could not hold the
model: still working, far slower than the latency targets assume.

That is the owner's decision from 2026-09-09 — keep the CPU fallback, make it
visible — expressed at the boundary. `health()` returns a note saying narration
will be slow and that the reader should be told. A log line does not satisfy
this; nobody using the reader is reading the logs.

### What it does not promise

**In-flight generation cannot be cancelled.** A torch forward pass runs to
completion inside one call and there is no safe way to interrupt it in process.
`timeout_seconds` bounds how long a caller waits *for a slot*, not how long the
GPU is busy. Claiming otherwise would surface later as a worker that reports a
timeout while still holding the device.

Concurrency is bounded in the adapter, not left to the caller, because the
caller cannot see the GPU. The default is one generation at a time: XTTS does
not fit twice in the VRAM this was developed on.

## Real-model smoke test

`scripts/smoke_synthesize.py` is the only thing here that loads the checkpoint.
It runs the fixed regression sentences through the normaliser, synthesises them,
applies the audio checks, and writes WAVs plus a JSON report.

It **does not run in CI**: it needs the 5.6 GB bundle and the full inference
stack, and CLAUDE.md requires real-model checks to run on trusted hardware and
be reported separately from fast pull-request checks.

```bash
SINHALA_TTS_MODEL_DIR=/path/to/xtts_si_female \
PYTHONPATH=src python scripts/smoke_synthesize.py --out ../../data/generated/smoke
```

Use an environment that already has torch, coqui-tts, and soundfile installed;
the manifest records which versions are load-bearing. `--cases plain-short` runs
a single case, which is worth doing first because loading the checkpoint on CPU
is slow.

A non-zero exit means a case failed an automated check. That is a signal to
listen, not a verdict on quality: **nothing automated here can tell you whether
the speech is intelligible or correctly pronounced.** That is why the WAVs are
written out, and why `data/generated/` is git-ignored — generated audio never
enters the repository.

## What the tests establish

`test_vendor_integrity.py` verifies the front end has not been altered, by
hashing it with line endings normalised so the check holds on any platform.

`test_text_frontend_characterisation.py` records what the front end **actually
does**, measured rather than assumed. It includes three behaviours that are
defects for a document reader, each marked `DEFECT`:

1. **Digits are silently deleted.** `"පිටුව 42 බලන්න"` → `"pituva balanna"`.
   Years, page numbers, prices, and decimals all vanish silently.
2. **Newlines and tabs are deleted, not collapsed**, gluing words together.
   PDF text is full of line breaks, so this corrupts roughly a word per line.
3. **English-only text is romanised as if Sinhala**: `"computer"` →
   `"chomputher"`. English inside a Sinhala sentence is unaffected, which is
   what makes it easy to miss.

These tests assert the defects on purpose. They are not approval of the
behaviour — they make it visible and make any change to it fail loudly.

## The rule for fixing those defects

**Wrap the front end; never edit it.** Its behaviour is what the model heard
during training, so changing it silently alters pronunciation and invalidates
the fine-tune. Number expansion and whitespace normalisation belong in a
normaliser that runs *before* `to_ascii()`, because the front end is lossy and
nothing can be recovered afterwards.

## The normaliser

`sinhala_tts.normalize` is that wrapper. Defects 1 and 2 are fixed there;
defect 3 is deliberately left alone, because changing English pronunciation on
reasoning alone would be a quality change adopted without a listening test.

```text
display text  ──to_speech_text()──▶  spoken text  ──to_model_input()──▶  model text
"පිටුව 42 බලන්න"                   "පිටුව හතළිස් දෙක බලන්න"        "pituva hathalis dheka balanna"
   store and display                  store alongside display          never store; only tokenise
```

The middle stage is deliberate. CLAUDE.md requires the spoken text to be kept
separate from the display text and forbids speech-expanded text being the only
source for display or retrieval — a reader searching for "42" must not be
matched against "හතළිස් දෙක". The middle stage is also the only one a reviewer
can read, which is what makes a pronunciation complaint diagnosable.

Callers must check `is_speakable()` before synthesising. Text can normalise to
nothing (a segment of only symbols), and synthesising an empty string produces
a silent clip that a cache would happily store as valid audio.

`NORMALIZER_VERSION` belongs in the audio cache key alongside the text hash,
document version, model version, voice, and generation settings. Bump it
whenever the produced text changes, or stale audio will be served.

### Numbers

`sinhala_numbers.py` writes cardinals 0–9999 as words: `42` → `හතළිස් දෙක`,
`2024` → `දෙදහස් විසි හතර`. The written forms were **reviewed and confirmed by
the project owner, a native Sinhala speaker, on 2026-09-09**.

Spelling confirmed is not pronunciation confirmed. The checkpoint was fine-tuned
on romanised ASCII, so a correctly written numeral can still be spoken badly.
That question is answered by listening to the smoke-test output, not by reading
the table.

If a number does sound wrong, the structure to re-check is the
standalone/combining split — `විස්ස` alone but `විසි` before another word,
`සියය` but `එකසිය`, `දෙදහස` but `දෙදහස්`. Correcting one entry fixes every
number that uses it.

Numbers of 10,000 and above are **not** attempted. Sinhala composition with
`ලක්ෂ` is more intricate, and a confident wrong form is worse than the digit
deletion this fixes, because it sounds right. Those are read digit by digit
instead — clumsy, but nothing is lost and nothing is invented.
