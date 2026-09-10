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
| Speech quality judged by listening | **Yes — ten sentences, 2026-09-10** |
| **Real book served through the reader API** | **Yes, on CPU — 2026-09-10** |
| GPU benchmark on serving hardware | No |

The checkpoint loads and produces audio through the documented procedure. See
"First measured run" below.

**2026-09-10: the output has now been listened to.** All ten regression
sentences were synthesised from the checkpoint and played by the project owner,
who reported no appended audio on any of them and judged all ten good. That
covers intelligibility, the conjuncts, mixed Sinhala-English, and — the cases
that mattered most — the three where the normaliser rewrote the text before the
model saw it: a page reference, a year, and a decimal percentage.

That listening also overturned something this document had recorded as a fault.
See "Appended audio: what it is and is not" below. **No GPU figures exist and
there are no latency claims here.**

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

### Text length: four different numbers, and the one that governs

| Source | Value | What it actually is |
| --- | --- | --- |
| `config.json` `gpt_max_text_tokens` | 402 | The checkpoint's limit, in **tokens** |
| `sinhala_text.py` docstring | 200 | Claims `GPTArgs.max_text_length = 200` |
| `voice-service` `MAX_TEXT_CHARS` | 1000 | An API guard, in **characters** |
| **`VoiceBpeTokenizer.char_limits["en"]`** | **250** | **The runtime guard, in characters** |

**250 characters is the operative limit for our path.** Read from the installed
`coqui-tts` source, not inferred: `char_limits` is keyed by language, `en` maps
to 250, and `check_input_length` is called from `preprocess_text` on every
inference. Over the limit it logs *"this might cause truncated audio"* and
proceeds — a warning, not a refusal.

Two consequences that matter more than the number:

- **Nothing splits the text for us.** `Xtts.inference` splits on the character
  limit only when `enable_text_splitting=True`; the default is `False` and the
  caller does not set it, so `text = [text]` and the whole segment is generated
  as one utterance. **Segmentation must enforce the limit itself.**
- **`voice-service` accepts 4× the model's own limit.** Its `MAX_TEXT_CHARS` of
  1000 would pass text the tokenizer warns about, in a warning easily lost among
  load messages.

The limit is also coherent with the audio ceiling, which is reassuring rather
than coincidental: 250 characters at the measured 10–11 characters per second is
about 23–24 s, and the derived audio-token ceiling is 25.8 s. The character limit
is essentially that ceiling expressed in characters.

So **cap segments at 250 characters of model input**, measured after
normalisation and romanisation, since that is the string the tokenizer sees.
Counting characters of the original Sinhala would be wrong: romanisation changes
length substantially, and `to_ascii` is applied before the tokenizer.

The 402-token and 200-token figures are not the runtime guard on this path. The
docstring's corpus statistics — median 59, p95 97, max 117 tokens per line —
remain useful as evidence that ordinary sentences sit far below every one of
these limits.

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
| `length_penalty` | 1.0 | `Xtts.inference` default |
| `repetition_penalty` | **10.0** | `Xtts.inference` default — **not** the config's 5.0 |
| `top_k` / `top_p` | 50 / 0.85 | `Xtts.inference` defaults, same as the config's |
| `do_sample` / `num_beams` | `True` / 1 | `Xtts.inference` defaults; sampling, not greedy |
| `enable_text_splitting` | `False` | `Xtts.inference` default |

**The config's generation settings are not in effect.** `Xtts.inference()`
carries its own defaults in its signature, and the caller passes only `text`,
`language`, the conditioning, `speed` and `temperature`. Anything not passed
takes the *method's* default, not the value in `config.json`.

For `top_k`, `top_p` and `length_penalty` the two agree, so it makes no
difference. For `repetition_penalty` they do not: the config says 5.0, the
method default is **10.0**, and 10.0 is what runs.

This was recorded incorrectly here at first, from reading `config.json` and
assuming an unpassed value falls back to it. Worth stating plainly because the
same assumption would misreport every future settings change: to know what a
run actually used, read the call site and the method signature, not the config.
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

## Appended audio: what it is and is not

**Corrected 2026-09-10.** This document previously reported a ~12% clean rate
and listed "a fix for the appended audio" as a blocker. That figure came from a
measure that does not work, and the blocker was smaller than stated.

### What happened

Ten regression sentences were synthesised and listened to. The automated
pause-based measure flagged **six**. The listener reported **none** — no
appended audio anywhere, and all ten good.

Measuring the waveforms settled which was right. `long-single-sentence` runs
continuously from 0.02 s to 12.10 s with no silence longer than 0.52 s; the
measure had reported "9.02 s of sound after the first utterance, across 5
regions". It had split a single sentence at its commas and called clauses two
onwards a fault.

Three of the six false positives were commas. The other three — `year`,
`page-reference`, `conjuncts` — have no punctuation at all: the pause follows an
expanded number, and is prosody rather than text. So a text-aware gate does not
fix it either, and one was tried and discarded.

Measured internal pauses now run to **0.86 s**, which completely covers the
0.26-0.70 s range that preceded genuine appended material. **No silence
threshold separates them.**

### What is still true

The original finding stands and is not withdrawn. Six runs of
`මම ගෙදර යනවා.` with identical settings gave 1.90, 2.27, 4.45, 4.31, 5.57 and
2.55 s, and the long ones were confirmed by listening to contain the sentence
followed by extra sound. Appended audio is real and stochastic.

### What detects it

Duration, not pauses. Against an expectation of 2.44 s for that sentence:

| Clip | Ratio | Verdict |
| ---: | ---: | --- |
| 1.90 s | 0.78x | clean |
| 2.27 s | 0.93x | clean |
| 2.55 s | 1.05x | clean |
| 4.45 s | **1.83x** | appended |
| 4.31 s | **1.77x** | appended |
| 5.57 s | **2.29x** | appended |

Perfect separation at `MAX_DURATION_RATIO`, and it passed all ten of the
2026-09-10 clips — including the three the pause measure flagged, which came in
at 1.14x, 1.11x and 1.04x.

So `check_audio` now decides on the duration ratio alone. The pause measure is
still computed and reported as context for a human, and **never fails a check**:
a check that fails on six of ten correct clips is one people learn to ignore,
and it nearly justified trimming that would have cut sentences at their commas.

### What this changes

- **Retry is not needed.** It was costed at multiples of GPU time against a
  ~12% clean rate that was not a clean rate.
- **Trimming stays rejected**, and now for a concrete reason rather than a
  cautious one: it would have truncated `long-single-sentence` at 3.40 s of 12.21.
- The remaining question is narrower — how often duration-detected appended
  audio actually occurs across many sentences. That needs a repeat run, and it
  needs the GPU decision first.

### Output duration is not stable between runs

The most important finding of this run, and the one most likely to affect the
product.

`මම ගෙදර යනවා.` — five words, model input `mama gedhara yanavaa.` — was
synthesised **six times in one process** with identical input and settings:

| Run | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duration | 1.90 s | 2.27 s | 4.45 s | 4.31 s | 5.57 s | 2.55 s |
| RMS | 0.086 | 0.086 | 0.082 | 0.082 | 0.082 | 0.085 |

**Spread 2.93×**, and a separate earlier run of the same sentence produced
6.77 s. All eight runs passed every automated check.

Generation is stochastic, so variation is expected and byte-identical output
must never be asserted. A near-3× spread in *duration* for a five-word sentence
is a different matter.

**The RMS is the informative part.** It stays between 0.082 and 0.086 regardless
of duration. If the extra length were trailing silence, RMS would fall roughly
in proportion — a 5.57 s clip with 2 s of speech would measure far quieter than
a 1.90 s clip that is all speech. It does not. So the longer outputs contain
*audio*, not padding.

#### Cause: confirmed by listening

**The project owner listened to `plain-short-1.wav` (1.90 s) against
`plain-short-5.wav` (5.57 s) on 2026-09-09 and confirmed the second contains the
sentence followed by extra sound.**

The model keeps generating after the sentence ends. This is a known XTTS failure
mode, and it is **not** a speech-rate difference.

Measuring the waveform envelope shows the structure. The sentence itself ends
between 1.00 s and 1.44 s in every clip; what varies is what follows:

| Clip | Sentence ends | Pause | Sound after the pause |
| --- | ---: | ---: | ---: |
| 1.90 s | 1.26 s | 0.62 s | none |
| 2.27 s | 1.44 s | 0.62 s | none |
| 4.45 s | 1.36 s | 0.44 s | 2.06 s |
| 4.31 s | 1.44 s | 0.70 s | 1.94 s |
| 5.57 s | 1.40 s | 0.52 s | 3.24 s |

The appended material is separated by a silence, which makes it detectable.
`sinhala_tts.speech_regions` does that, and `check_audio` reports it when the
caller declares the text was a single sentence.

**It is not rare.** Across the eight smoke cases and six variance runs, appended
audio was detected in roughly half. Some of those are false positives —
`plain-longer` genuinely holds two sentences, and a pause before an English
acronym looks the same to a detector — but `plain-short` at 3.42 s of appended
sound is not one of them.

#### Why detection, and not trimming

The detector reports; it does not cut. Automatically trimming risks truncating
real speech, and for a reader used by people who cannot see the page, silently
dropping the end of a sentence is far worse than a stretch of unwanted sound: a
listener can tell that trailing noise is not part of the book, but cannot tell
that a sentence was cut short.

The thresholds also do not separate the cases cleanly. Measured pauses *inside*
speech were 0.16–0.26 s and pauses *before* appended material were 0.26–0.70 s.
Those ranges overlap, so no threshold can be both safe and complete.

#### Generation settings do not fix it

Tested on 2026-09-09 with `scripts/settings_experiment.py`: the fixed sentence
`මම ගෙදර යනවා.`, four runs per configuration, one variable changed at a time.

| Configuration | Clean | Median duration | Mean appended |
| --- | ---: | ---: | ---: |
| baseline | 1/4 | 3.80 s | 1.38 s |
| temperature 0.30 | 0/4 | 4.94 s | 2.49 s |
| top_k 20, top_p 0.60 | 0/4 | 3.76 s | 1.99 s |
| length_penalty 0.5 *(inert, see below)* | 0/4 | 3.78 s | 1.46 s |
| repetition_penalty 5.0 | 2/4 | 2.85 s | 0.99 s |
| greedy (`do_sample=False`) | 0/4 | 3.43 s | 0.90 s |

**No configuration eliminated the appended audio.**

**The decisive result is greedy.** With sampling disabled, all four runs
produced *identical* output — 3.43 s, 0.90 s appended, every time. Determinism
works, and the model still appends. So this is **not a sampling excursion; it is
learned behaviour**, and no decoding strategy will remove it. That closes off
the whole category of fixes.

The owner listened to `greedy-1.wav` and confirmed the appended 0.90 s is
audible follow-up noise. That matters twice over: it rules greedy out as a fix,
and it confirms the detector's reading corresponds to something a listener
actually hears at *small* magnitudes, not only in the obvious three-second
cases.

Two secondary findings:

- **Lower temperature made it worse**, not better (2.49 s mean appended against
  the baseline's 1.38 s). The hypothesis that a more conservative sampler would
  stop more reliably was simply wrong.
- **`length_penalty` was never applied.** Transformers ignores it when
  `num_beams == 1`, which is XTTS's default, and says so in a warning that is
  easy to miss among load messages. Confirmed by reading the validation source.
  Those four runs are therefore extra baseline samples, not a tested variation —
  which puts the baseline at **1 clean run in 8**, or about 12%.
- `repetition_penalty` 5.0, the value `config.json` documents but the caller
  never passes, was the best of the six at 2/4. With four runs that is not a
  result, only a reason to test it properly.

#### Trimming was evaluated, and it is unsafe

Implemented as `trim_to_first_utterance` and evaluated on 2026-09-09 against
sentences chosen to make it fail: one with two commas, and one long multi-clause
sentence. It failed them.

The clean runs — the ones the detector left alone — give a speech-rate baseline
of **10–11 characters of model input per second**. Comparing that against what
survives trimming:

| Case | Characters | Clean rate | Rate after trimming | |
| --- | ---: | ---: | ---: | --- |
| `page-reference` | 30 | 10.0 c/s | 14.1–18.9 c/s | partly cut |
| `comma-clauses` | 45 | 11.0 c/s | 23.6–24.9 c/s | about half cut |
| `long-single-sentence` | 194 | — | **59–60 c/s** | about 80% destroyed |

Nothing speaks at 60 characters a second. The trimmer cut those sentences apart
at their own comma pauses, keeping 3.2 s of a 12.3 s sentence and discarding the
rest — exactly the silent truncation the earlier increment refused to risk, now
demonstrated rather than hypothesised.

**Trimming at the first long pause is rejected.** The code stays, unused and
documented as dangerous, because the evaluation is worth keeping runnable.

#### The detector over-flags realistic prose

The same evaluation exposed a fault in the detector itself. On
`long-single-sentence` it reported "7.68 s of sound after the sentence ended
across 3 speech regions" — but those three regions are the sentence's own
comma-separated clauses. The whole 12.3 s is real speech.

So `expect_single_utterance` is **reliable only for short sentences without
internal pauses**, and must not gate anything on real document text as it
stands.

#### Speech rate is not constant, and assuming it was misled me

Calibration run, 2026-09-09: ten cases, three repeats, thirty clips. Apparent
speed climbs steadily with text length, measured on clips with no appended
audio:

| Characters | Characters per second |
| ---: | ---: |
| 21 | 7.7–8.7 |
| 30 | 9.8–10.0 |
| 44 | 12.0–12.5 |
| 71 | 13.9–14.2 |
| 194 | 14.9–15.4 |

Every clip carries a fixed overhead — onset, leading and trailing silence —
which weighs proportionally more on a short one. Fitting overhead plus a
marginal rate gives:

```text
duration ≈ 1.2 s + characters / 17
```

It predicts 2.94 s for 30 characters against 2.92 measured, and 12.61 s for 194
against 12.58.

**This retracts the content-loss suspicion recorded earlier.** The long sentence
looked short only because "expected" was computed from a rate measured on short
clips, where overhead dominates. At 194 characters it sits exactly on the curve.
There is no evidence the model drops content on long input, and the earlier
entry saying there might be was wrong.

#### The rule that replaces the gap rule

Flag a clip when its duration exceeds **1.4x** the expected duration above.
Implemented in `audio_checks.check_audio`; `expect_single_utterance` and its
gap-based rule are retained for diagnosis but no longer gate anything.

Validated against **all 80 clips generated so far**, across every experiment:

| Text | Ratio to expectation | Verdict |
| --- | --- | --- |
| `long-single-sentence`, 6 clips | 0.96–1.05x | clean — gap rule flagged all six |
| `comma-clauses`, 6 clips | 0.93–1.17x | clean — gap rule flagged four |
| `plain-longer`, `year`, `line-broken`, `conjuncts`, `page-reference` | 0.89–1.07x | clean |
| `plain-short`, runs confirmed clean by listening | 0.78–1.05x | clean |
| `plain-short`, runs confirmed faulty by listening | 1.62–2.78x | flagged |
| `greedy`, confirmed faulty by listening | 1.41x | flagged |

**Zero false positives on multi-clause prose**, which is what made the gap rule
unusable, and every clip the owner listened to lands on the correct side.

Two honest limits:

- **The margin is thin.** Greedy, confirmed faulty by ear, sits at 1.41x against
  a 1.4x threshold. Known-good prose reaches 1.17x and one unconfirmed clip
  reaches 1.39x. The 1.2–1.4x band is unexamined, so the threshold separates the
  cases we have checked and not much more.
- **Calibrated on CPU, one voice, ten sentences.** Re-fit on serving hardware
  and on real document text before this gates a release.

#### Where that leaves the fix#### Where that leaves the fix

Retrying a flagged segment still works, because sampling makes each attempt
independent — but the arithmetic is poor. At the measured ~12% clean rate, four
attempts reach only about 40%. Even at `repetition_penalty` 5.0's optimistic
50%, four attempts cost four times the GPU for 94% coverage. For narrating whole
books that is a serious cost, not a rounding error.

Settings cannot fix it, and trimming at the first pause destroys real sentences.
So the options are now:

1. ~~Replace the gap rule with a duration-expectation rule.~~ **Done**, fitted
   to 30 clips and validated against all 80. It no longer flags ordinary prose.
2. **Establish whether `repetition_penalty` 5.0 genuinely helps**, with 20+
   repeats. It is the documented value we are not using, and it was the best of
   the six tested.
3. **Bounded retry**, once the detector is trustworthy enough to decide what to
   retry. At the measured ~12% clean rate this is expensive, and retrying a
   false positive would loop on audio that was never faulty.
4. ~~Investigate whether long input loses content.~~ **Resolved:** the
   calibration shows speech rate rises with length because of fixed overhead.
   The long sentence sits exactly on the fitted curve; nothing is being lost.

Trimming stays implemented but unused, its danger documented and a test
asserting that it destroys a second sentence. Keeping the evaluation runnable is
worth more than deleting the code.

This is a release blocker for narration quality, not a cosmetic issue.

This is measured, not resolved, and it has consequences:

- Segment length cannot be predicted from text length, so any chunking bound
  derived from characters or tokens needs a margin against the model's 25.8 s
  ceiling rather than a tight fit.
- Latency targets must be stated as percentiles over repeated measurements. A
  single timing is close to meaningless.
- An output-length sanity check belongs in the serving path, not only in the
  smoke test — but its thresholds have to be calibrated against listening first.
  The current `MIN_CHARS_PER_SECOND` of 2.0 passed every one of these runs,
  including the 6.77 s one, which is exactly the "provisional and uncalibrated"
  caveat in `audio_checks.py` proving itself in practice.
- If the cause is trailing generation, the fix is upstream of thresholds —
  generation settings, or trimming against a detected end of speech — and must
  be evaluated by listening rather than by duration alone.

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

## First run through the API, on a real book

2026-09-10. Everything above measures the model in `services/tts`, driven by a
script. This is the first time the checkpoint served a **real book through the
real API**: `SINHALA_READER_TTS=xtts`, a uvicorn server, and the reader's own
routes, on the Grade 11 Sinhala history textbook.

It matters because the two halves had never met. Every API measurement before
today was a 440 Hz tone; every model measurement was eight sentences chosen to
exercise the normaliser. This is 26 consecutive segments of a page nobody
selected.

**Still CPU, still not a performance claim.** `torch 2.13.0+cpu`, so no GPU
figure can come from this machine at all.

| | |
| --- | --- |
| Upload and preparation | 31.8 s → 168 pages, 2,829 segments |
| Page 152 | 26 segments |
| First audio, cold | 165.9 s — includes the 5.6 GB checkpoint load |
| Steady state | 3.58–4.07× real time, median 3.75× |
| Cached re-fetch | 4–7 ms |
| Sample rate | 24000 Hz on every segment |
| `X-Reader-Real-Model` | `true` on every segment |
| `model_version` | `ce18fe82442ccbd3`, recorded per segment |

Readiness behaved correctly at both ends. While the checkpoint loaded it
reported `"readiness": "loading"` with the cold-start limitation named; once
serving it reported `"ready"` with the model version. Neither call blocked on
the load, which is the property `loaded_model_version` exists to protect.

### The 250-character limit holds, across all 2,829 segments

This was the riskiest untested assumption in the whole pipeline. Segmentation
caps segments at 250 characters of **model input**, and romanisation expands
Sinhala substantially — on this page, 195 source characters became 246.

Across the 26 segments the longest model input was **exactly 250**. A cap
landing precisely on its limit is either a coincidence or a segmenter doing its
job, so all 2,829 segments of the book were then measured — segmentation and
romanisation only, no synthesis needed:

| | |
| --- | --- |
| Segments | 2,829 |
| Model-input characters | min 1, median 120, p95 247, p99 250, **max 250** |
| Exactly at the limit | 33 |
| Within 5 of the limit | 215 |
| **Over the limit** | **0** |
| Normalising to nothing speakable | 0 |

So the cap is doing its job across the whole book, not coincidentally on one
page. That matters because over the limit XTTS logs *"this might cause truncated
audio"* and continues — a reader would lose the end of a sentence with no error
raised anywhere.

The longest segment implies about 15.9 s of audio at the measured 17 characters
per second, comfortably under the derived 25.8 s utterance ceiling. The two
limits are consistent, and the character cap is the binding one.

### Appended audio: 26 of 26 pass

The duration check — the one that replaced the pause measure — was run over all
26 clips. Ratios ranged 0.85× to 1.26× against a band of 0.5–1.4×.

This is the first evidence on text nobody chose for the model's benefit, and it
partly answers the "does it hold across a book" question that ten sentences
could not. It does not close it: 26 consecutive segments of one page is not a
book, and a stochastic fault that appeared three times in six identical runs can
be absent from 26 different ones by chance.

### What this says about the 5-second target

CLAUDE.md's provisional target is a first short synthesised segment within 5 s
at p95 on declared hardware. On this page:

| | |
| --- | --- |
| Page 152 | 4.3 min of audio, 14.3 min of compute at steady state |
| Whole book | ~7.4 h of audio, ~28 h on this CPU |

The ~28 h supersedes an earlier ~16 h estimate extrapolated from the regression
sentences, which are shorter than real textbook segments.

More usefully, the target looks **structural rather than purely a hardware
question**. A 250-character segment is ~16 s of audio and ~60 s of compute here.
Even a tenfold speedup leaves a full-length first segment at ~6 s. Meeting 5 s
at p95 probably requires the *first* segment of a request to be short — a
segmentation and product decision — not only faster hardware. Worth settling
before hardware is chosen, because it changes what the hardware has to do.

### One segment took 1,099 seconds, and it was not the text

Segment 6 of page 152 took **1,099 s** to produce 16.3 s of audio — a real-time
factor of 67×, against 3.6–4.1× for everything else on the page. Segment 4 is
the same 195 source characters, the same 246 characters of model input, and
ordinary prose from the same page; it took 74 s.

Its output was normal: 16.3 s of audio, well inside the expected duration, so
nothing ran away or looped. Only the compute was anomalous.

Both segments were then re-synthesised three times each in one process:

| | Run 1 | Run 2 | Run 3 | First run, through the API |
| --- | ---: | ---: | ---: | ---: |
| Segment 6 | 64.3 s | 63.0 s | 63.1 s | **1,099.4 s** |
| Segment 4 | 69.5 s | 66.6 s | 73.4 s | 73.7 s |

Real-time factors across all six: 3.81–3.91×. **Segment 6 is an ordinary
segment.** The text is not the cause, so this is not a fault that would follow
the model onto a GPU.

What the cause *was* is not established — it did not reproduce, and a
one-off that cannot be reproduced cannot be diagnosed from one sample. The
plausible explanation is contention on the development machine during that
window, and it is recorded here rather than explained away because a 15×
latency excursion on a shared serving host would be a real operational
problem even when the model is blameless. Queue-time and per-segment latency
monitoring should make such an excursion visible; that belongs with the GPU
deployment work, not here.

The repeats also add a data point to "Output duration is not stable between
runs" above, at a length that section did not cover: segment 4 produced 17.13 s,
17.78 s, 18.53 s and 19.22 s from identical input across four runs. That is a
spread of 1.12×, against the 2.93× measured on a five-word sentence. On this
evidence the instability is proportionally *smaller* on long segments than short
ones — worth knowing, since real book segments are long.

## The adapter

`sinhala_tts.adapter` implements the boundary CLAUDE.md asks for,
`synthesize(text, voice_id, settings) -> audio + metadata`, and everything in
"Known working inference procedure" above is encoded in it rather than repeated
by each caller.

Validated against the real checkpoint on 2026-09-09:

```text
before load: not_loaded            serving: False
after load : degraded  (61 s)      device: cpu
  note: Running on CPU after the GPU could not hold the model. Narration will be
        much slower than usual; tell the reader rather than letting them wait.
synthesis  : 3.01 s @ 24000 Hz, checks OK, real model, version ce18fe82442ccbd3
second call: 11 s, no reload
```

That run confirms four things the interface promises:

- The model is loaded **once per process**: the second call skipped the 61 s
  load entirely.
- **Readiness is not liveness.** The adapter reported `not_loaded` and
  `serving: False` before loading, which a naive health check would have called
  healthy.
- **The CPU fallback is visible**, as decided. `DEGRADED` is a distinct state
  and `health()` carries a note written for the reader, not for a log.
- Every segment carries its model version, device, settings, and cache key.

`DevelopmentAdapter` is the labelled placeholder that lets the rest of the
application be built without the bundle. It emits a tone, never speech; its
results carry `is_real_model=False` and a `development-` voice id; and that flag
is part of the cache key, so a placeholder cannot be served from cache as
narration.

**Cancellation is deliberately not promised.** A torch forward pass cannot be
interrupted in process, so `timeout_seconds` bounds waiting for a slot, not the
generation itself. Concurrency is bounded in the adapter at one generation by
default, because the caller cannot see the GPU.

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

- **How often appended audio actually occurs.** 26 consecutive segments of a
  real page passed the duration check on 2026-09-10, which is better evidence
  than one sentence repeated six times but still one page. A stochastic fault
  can be absent from 26 clips by chance.
- **Listening beyond ten sentences.** Ten were heard on 2026-09-10 and all were
  good. 26 more exist from the API run and have not been listened to. Neither is
  yet an answer to "does it hold across a book".
- GPU figures: first-audio latency, real-time factor, sustained throughput, and
  peak VRAM on serving hardware. The CPU run recorded above is not a substitute.
- Whether the derived 25.8 s utterance ceiling matches observed behaviour.
- Whether the checkpoint carries optimizer or training state, and whether an
  inference-only artifact is worth extracting.
- Container and GPU runtime compatibility.
- Licence position: XTTS-v2 weights are published under CPML, which is
  non-commercial, and fine-tuning does not automatically remove it. Unresolved.
- Permission to use the supplied speaker reference audio for public release.
