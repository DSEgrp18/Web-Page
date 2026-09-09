# Sinhala XTTS inference manifest

Recorded 2026-09-09, per the "Integrating the existing model" and "MLOps scope"
requirements in [CLAUDE.md](../CLAUDE.md).

Everything here was **read from the actual model bundle and the owner's working
inference service**, not copied from the seed project's notes. Where a value is
derived or still unverified, this document says so. Nothing in it is a
performance claim.

## Status

| | |
| --- | --- |
| Model assets inspected | Yes |
| Working inference implementation inspected | Yes |
| Text front end behaviour measured | Yes — see `services/tts/tests/` |
| **Real synthesis run from this repository** | **Yes, on CPU — 2026-09-09** |
| Speech quality judged by listening | Not yet |
| GPU benchmark on serving hardware | No |

The checkpoint loads and produces audio through the documented procedure. See
"First measured run" below. Nobody has listened to the output yet, and no GPU
figures exist, so there are no quality or latency claims here.

## Artifact identity

Bundle location, set by configuration and never committed:
`models/xtts_si_female/` (git-ignored; delivered out of band).

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `model.pth` | 5,607,762,519 | `0651887b8bdfb8746a78f5a573244ce7d6d460a841419c9fcbcabeb7b19a90ab` |
| `vocab.json` | 376,645 | `9493774aef40a61e0027b5e5e774c93c2c81579eafaed3048156bc2bd12c135a` |
| `config.json` | 4,526 | `f87f05aacee1589823d8c802f4eaa89e24239c123b6d8117ab1895bcfdc5c831` |
| `sinhala_text.py` | 10,652 | `f8f41fa44de13bb93a6f1de47a6b1d1aabc3162feadd6171c170ea8520919c92` |
| `reference.wav` | 271,916 | `fa1e2295086beef1f8a738435c30a9f5696379187bbd155459928bd2a49dab23` |

Computed on 2026-09-09 from the bundle in this workspace. These are the identity
of the artifact a release loads; a deployment must resolve to these values and
record what it actually loaded.

Sizes match those recorded in `CLAUDE.md`. All five files must stay together;
the tokenizer and the speaker reference are not interchangeable.

`sinhala_text.py` is vendored into this repository at
`services/tts/src/sinhala_tts/vendor/`, because inference must use the same text
front end as training and the bundle is not on any teammate's machine. Its
integrity is checked by CI. See its `PROVENANCE.md`.

## Consistency checks performed

These passed, and are worth re-running whenever the bundle is replaced:

- `vocab.json` contains exactly **6,681** tokens, matching
  `model_args.gpt_number_text_tokens: 6681` in `config.json`. A tokenizer that
  does not match the checkpoint would mis-map every token.
- `vocab.json` declares `unk_token: "[UNK]"` and a `Whitespace` pre-tokenizer,
  confirming the front end's stated reason for existing: one unknown codepoint
  turns an entire word into `[UNK]`.
- `reference.wav` is mono, 24 kHz, 16-bit, 5.664 s.

## Architecture and limits, from `config.json`

| Property | Value | Consequence |
| --- | --- | --- |
| `model` | `xtts` | XTTS-v2 (`gpt_use_perceiver_resampler: true`) |
| `model_args.output_sample_rate` | 24000 | Generated audio is 24 kHz |
| `model_args.input_sample_rate` | 22050 | Speaker conditioning is resampled to 22.05 kHz |
| `gpt_max_text_tokens` | 402 | Upper bound on text tokens per generation |
| `gpt_max_audio_tokens` | 605 | Upper bound on audio tokens per generation |
| `gpt_code_stride_len` | 1024 | Samples per audio token |
| `gpt_number_text_tokens` | 6681 | Must equal the tokenizer's vocabulary size |
| `gpt_max_prompt_tokens` | 70 | Conditioning prompt budget |

**Derived maximum utterance length: about 25.8 seconds.**
605 audio tokens × 1024 samples ÷ 24000 Hz = 25.81 s. Any chunk whose speech
would exceed this is truncated by the model rather than failing loudly, so
segmentation must stay well inside it. This is a derivation from the config, not
a measurement; confirm it against real output before relying on it.

### Text length: three different numbers, none of them interchangeable

This is the single easiest thing to get wrong, so all three are recorded:

| Source | Value | What it actually is |
| --- | --- | --- |
| `config.json` `gpt_max_text_tokens` | 402 | The checkpoint's own limit, in **tokens** |
| `sinhala_text.py` docstring | 200 | Claims `GPTArgs.max_text_length = 200` |
| `voice-service` `MAX_TEXT_CHARS` | 1000 | An API guard, in **characters** |

The docstring also reports measured corpus statistics of median 59, p95 97, and
max 117 tokens per line. CLAUDE.md is explicit that chunks must be bounded by
actual model limits rather than a copied character cap, so **segmentation must
count tokens with the real tokenizer**, not characters. Which of 402 and 200
binds in practice has not been tested and must be measured before chunking is
finalised.

## Language token

**`language="en"`. Confirmed, not inferred.**

`config.json` lists XTTS's stock 17 languages and does **not** include `si`.
That list describes the base model and says nothing about this fine-tune.

The fine-tune romanises Sinhala into ASCII the base model already tokenises and
trains under the English token, so the task becomes learning an accent rather
than a script. This is stated in the front end's own docstring, is confirmed by
its self-test encoding text as `"[en]" + ...`, and is what the owner's working
service passes at inference.

Two traps, both of which CLAUDE.md warns about and both of which are real here:

- Taking the last entry of the `languages` list would select **Hindi** (`hi`).
- Assuming the UI language is the inference token would select `si`, which the
  model does not have.

The working service resolves this by defaulting to `en` and only trusting the
config when a fine-tune has genuinely added `si` to its own language list. That
behaviour should be preserved.

## Known working inference procedure

Taken from the owner's `PDF-Tool/voice-service`, which is a working
implementation. Preserve these settings initially; change them only with
measured justification.

### Load (once per worker process, never per request)

```python
config = XttsConfig()
config.load_json(".../config.json")
model = Xtts.init_from_config(config)
model.load_checkpoint(
    config,
    checkpoint_path=".../model.pth",
    vocab_path=".../vocab.json",
    use_deepspeed=False,
)
model.eval()
```

On GPU the working service calls `model.cuda()` then `model.half()` (fp16 by
default), because XTTS in fp32 does not fit the 4 GB card it was developed on.

### Speaker conditioning (computed once, cached for the process)

`reference.wav` is read with **soundfile**, mixed to mono, and resampled to
22,050 Hz, then:

```python
gpt_cond_latent = model.get_gpt_cond_latents(
    audio, sr, length=config.gpt_cond_len, chunk_length=config.gpt_cond_chunk_len)
speaker_embedding = model.get_speaker_embedding(audio, sr)
```

`config.json` gives `gpt_cond_len: 30`, `gpt_cond_chunk_len: 4`,
`max_ref_len: 30`, `sound_norm_refs: false`.

Two details that cost real debugging time and must not be lost:

- The convenience path `get_conditioning_latents(audio_path=...)` routes audio
  IO through **torchcodec** from torch 2.9, which needs FFmpeg's native
  libraries installed system-wide. Reading the WAV with soundfile and calling
  the lower-level methods avoids that dependency entirely.
- The reference tensor must match the model's **device and dtype**. A float32
  reference against a half-precision model fails deep inside the GPT forward
  pass with an error naming neither dtype nor the function responsible.

### Synthesis

```python
out = model.inference(
    text, language, gpt_cond_latent, speaker_embedding,
    speed=speed,
    temperature=0.65,
)
```

| Setting | Value | Source |
| --- | --- | --- |
| `temperature` | **0.65** | Working service, deliberately overriding the config's 0.75 — a book reader wants consistency between sentences more than expressive variation |
| `length_penalty` | 1.0 | `config.json` default, not overridden |
| `repetition_penalty` | 5.0 | `config.json` default, not overridden |
| `top_k` / `top_p` | 50 / 0.85 | `config.json` defaults, not overridden |
| `speed` | clamped to 0.5–2.0 | Working service; outside this range audio degrades badly |

Output is a float32 waveform at 24 kHz. The working service clips to [-1, 1]
before writing 16-bit PCM, because XTTS occasionally overshoots and integer
wraparound turns an overshoot into a full-scale click.

Generation is **serialised under a per-voice lock**: 4 GB of VRAM does not fit
two concurrent generations.

## Runtime dependencies

Verified working on the owner's machine with Python **3.13.7**.

| Requirement | Note |
| --- | --- |
| `torch`, `torchaudio` | Installed **first** and separately. `coqui-tts` declares neither, so installing requirements alone appears to succeed and then fails at model load |
| CUDA wheel index | `cu126` or newer. **Not `cu121`** — it has no Python 3.13 wheels, and pip's error does not say so |
| `coqui-tts` | The XTTS implementation |
| `transformers` | **`>=4.57,<5`**, load-bearing. transformers 5 removed `isin_mps_friendly`, which `coqui-tts` still imports; unpinned installs resolve to 5.x and synthesis dies on the first request |
| `soundfile`, `numpy` | Audio IO |
| `torchcodec` | **Not required, deliberately** — see conditioning above |

These pins were measured in the owner's runtime. Re-verify them in the container
before trusting them there; CLAUDE.md is explicit that package pins must not be
copied between projects without testing.

## First measured run

2026-09-09, `services/tts/scripts/smoke_synthesize.py`, on the development
machine. **These are CPU numbers and are not a performance claim.** They exist
to prove the pipeline works end to end and to give later GPU figures something
to be compared against.

| | |
| --- | --- |
| Device | CPU (`torch 2.13.0+cpu`; CUDA not available in that environment) |
| Precision | fp32 |
| Model load | 66-112 s across runs |
| Speaker conditioning | 0.9-1.8 s (once per process, then cached) |
| Language token | `en` |
| Temperature | 0.65 |

All eight regression cases were synthesised and **all eight passed** the
decoded-sample checks: 24 kHz as expected, non-silent (RMS 0.079–0.088), no
clipping, no truncation.

| Case | Audio | Synthesis | Real-time factor |
| --- | ---: | ---: | ---: |
| `plain-short` | 6.77 s | 67.6 s | 9.99× |
| `plain-longer` | 5.19 s | 31.9 s | 6.15× |
| `page-reference` | 3.01 s | 15.9 s | 5.28× |
| `year` | 4.60 s | 31.0 s | 6.75× |
| `decimal-and-percent` | 4.09 s | 22.7 s | 5.55× |
| `mixed-english` | 2.92 s | 13.8 s | 4.72× |
| `conjuncts` | 4.03 s | 17.5 s | 4.34× |
| `line-broken` | 3.48 s | 14.6 s | 4.21× |

The normaliser reached the model intact in every case:

| Display | Model input |
| --- | --- |
| `පිටුව 42 බලන්න.` | `pituva hathalis dheka balanna.` |
| `2024 වර්ෂයේ දී එය සිදු විය.` | `dhedhahas visi hathara varshayee dhii eya sidhu viya.` |
| `ප්‍රතිශතය 12.5% ක් විය.` | `prathishathaya siyayata dholaha dhashama paha k viya.` |
| `මෙම වාක්‍යය\nදෙකට කැඩී\nඇත.` | `mema vaakyaya dhekata kaedii aetha.` |

Numbers, the percent marker moving in front of its number, decimals read digit
by digit, and line breaks becoming spaces all survive to the model.

### Output duration is not stable between runs

`plain-short` produced **2.13 s** of audio in one run and **6.77 s** in another,
from identical input and identical settings — a factor of 3.

Generation is stochastic, so some variation is expected and byte-identical
output must never be asserted. A 3× spread in *duration* for a five-word
sentence is a different matter: it suggests the model is appending material
beyond the sentence, which is a known XTTS failure mode. Nobody has listened
yet, so whether the longer output is slower speech, a trailing artefact, or
babble is **unknown**.

This is measured, not resolved, and it has consequences:

- Segment length cannot be predicted from text length, so any chunking bound
  derived from characters or tokens needs a margin against the model's 25.8 s
  ceiling rather than a tight fit.
- Latency targets must be stated as percentiles over repeated measurements. A
  single timing is close to meaningless.
- An output-length sanity check belongs in the serving path, not only in the
  smoke test — but its thresholds have to be calibrated against listening first,
  because the current `MIN_CHARS_PER_SECOND` of 2.0 passed the 6.77 s run.

What this establishes:

- The documented load procedure is correct, including the soundfile
  conditioning path that avoids torchcodec.
- `language="en"` produces audio rather than failing, consistent with the
  fine-tune being trained under that token.
- The normaliser reaches the model intact: `පිටුව 42 බලන්න.` was synthesised as
  `pituva hathalis dheka balanna.`, and its audio is 1.2 s longer than the
  shorter sentence — the expanded number is present in the output rather than
  being dropped as it was before.

What it does **not** establish:

- **Anything about quality.** No one has listened. The checks confirm the audio
  is not silent, not clipped, and not truncated; they cannot tell whether the
  speech is intelligible, correctly pronounced, or even Sinhala.
- Anything about serving latency. Real-time factors of 4-10× mean synthesis
  takes that many times longer than the audio lasts, which is a CPU
  characteristic, not a property of the model. The 5 s first-segment target in
  CLAUDE.md cannot be assessed until this runs on a GPU.
- Anything about VRAM, since none was used.

## Hardware observed

The development machine has an **NVIDIA GeForce RTX 2050 with 4 GB VRAM**
(driver 592.82). XTTS wants roughly 4–6 GB, so this card is expected to
out-of-memory and fall back to CPU. Real-model smoke tests are possible here but
will be slow and are not representative of serving hardware.

No GPU serving host has been chosen or measured.

## CPU fallback: decided

The working service falls back to CPU automatically on CUDA OOM, both at load
time and mid-inference, and logs a warning. CLAUDE.md says the opposite:

> never silently substitute voices or move overloaded inference to CPU

**Decision, taken by the project owner on 2026-09-09: keep the fallback, but
make it visible.** A slow voice beats no voice, so the fallback stays; what
CLAUDE.md actually objects to is the silence, not the CPU.

That means, when the adapter is built:

- Degraded mode is reported through readiness, distinctly from "not loaded" and
  from "healthy on GPU". Process liveness, model readiness, and degraded
  performance are three different states.
- The reader is told, accessibly, that narration is currently slower than usual.
  A politely announced status, not an alert, and not a silent stall.
- The generated segment records which device produced it, so a latency
  regression can be attributed rather than guessed at.
- A log line alone does not satisfy this. Nobody reading the application is
  reading the logs.

`scripts/smoke_synthesize.py` already follows this: its OOM path prints a
warning and records the device actually used in the report.

## Text front end

`to_ascii()` from the vendored `sinhala_text.py` is **required**. Skipping it
does not lower quality, it destroys the output: the Sinhala block is absent from
the vocabulary, so every Sinhala word becomes `[UNK]` and the model emits
fluent-sounding babble.

Measured behaviour is locked in by
`services/tts/tests/test_text_frontend_characterisation.py`. Three findings are
defects for a document reader. They are fixed by a normaliser that runs
**before** the front end, never by editing it. `sinhala_tts.normalize` now does
this for the first two; the third is deliberately left alone.

1. **Digits are silently deleted.** `_KEEP` contains no digits, so
   `"2024 වර්ෂය"` → `"varshaya"` and `"පිටුව 42 බලන්න"` → `"pituva balanna"`.
   Years, page references, prices, decimals, and list numbering all vanish with
   no indication to the listener.
   **Fixed** by `sinhala_numbers.py`, which writes cardinals 0–9999 as Sinhala
   words before the lossy step. Its word forms still need native-speaker review,
   and 10,000 and above is read digit by digit rather than guessed at.
2. **Newlines and tabs are deleted rather than collapsed**, joining the words on
   either side: `"line one\nline two"` → `"line oneline thwo"`. PDF-extracted
   text is full of line breaks, so this would corrupt roughly one word per line
   of a real document.
   **Fixed** by `normalize_whitespace()`, which also strips soft hyphens and
   zero-width spaces — PDF layout inserts them mid-word — while preserving
   U+200D, which is meaningful in Sinhala conjuncts.
3. **English-only text is romanised as if it were Sinhala**, because the
   dispatch checks whether *any* Sinhala codepoint is present: `"computer"` →
   `"chomputher"`. English *inside* a Sinhala sentence is unaffected, which is
   what makes this easy to miss.
   **Deliberately not fixed.** Calling `sinhala_to_ascii()` directly instead of
   `to_ascii()` would skip the fold and leave `"computer"` intact — a one-line
   change. It is not adopted because it changes pronunciation on the basis of
   reasoning alone. This is a listening comparison to run, not a bug to patch:
   the model was fine-tuned under the `en` token on folded ASCII, so which
   spelling it renders better for English words is an empirical question.
   `contains_sinhala()` is exposed to make that experiment easy.

A fourth, minor: the module's own docstring lists `(`, `)` and `=` in its output
charset. They are stripped. Trust the tests, not the docstring.

## Not yet established

Required by CLAUDE.md before serving, and still missing:

- **Listening.** Nobody has heard any generated audio. Every quality question —
  intelligibility, pronunciation, whether the written-out numbers sound right —
  is open until someone plays the smoke-test WAVs. The written number forms are
  confirmed; how they sound from this model is not.
- GPU figures: first-audio latency, real-time factor, sustained throughput, and
  peak VRAM on serving hardware. The CPU run recorded above is not a substitute.
- Whether 402 or 200 text tokens binds in practice, measured with the real
  tokenizer.
- Whether the derived 25.8 s utterance ceiling matches observed behaviour.
- Whether the checkpoint carries optimizer or training state, and whether an
  inference-only artifact is worth extracting.
- Container and GPU runtime compatibility.
- Licence position: XTTS-v2 weights are published under CPML, which is
  non-commercial, and fine-tuning does not automatically remove it. Unresolved.
- Permission to use the supplied speaker reference audio for public release.
