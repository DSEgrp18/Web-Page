# services/tts/deploy

The voice, on Modal.

This is the one part of the system that does not run on our own server, and it
is here because GPU inference is the single forced split CLAUDE.md allows. See
[`modal_app.py`](modal_app.py) for the deployment itself.

**Nothing here has been run yet.** No Modal deployment exists, no GPU number for
this model exists, and every performance statement in this directory is a
prediction derived from CPU measurements. The `verify` entrypoint is what turns
them into facts.

## What crosses the boundary

Spoken text goes out. WAV bytes and synthesis metadata come back.

That is the whole interface, and it is deliberately that small. The reader's
PDF, the extracted text, the document identity and the reader identity all stay
on our own server, so a student's private textbook never reaches a third-party
compute provider. Anything added here that needs the document itself should be
treated as a design mistake rather than a feature.

## Before the first deploy

You need a Modal account, `pip install modal`, and `modal setup`.

### 1. The weights

The bundle is 5.6 GB, is not in Git, and does not exist on anyone's machine
except by out-of-band delivery. It goes on a Modal Volume — not into the image.

Baking 5.6 GB into the image would push it through every deploy and, worse, tie
the weights to the application's release cycle. CLAUDE.md is explicit that model
weights must not be replaced by an ordinary application deployment; a Volume
keeps those two things separate, so a code deploy cannot silently change the
voice.

```bash
modal volume create sinhala-xtts-si-female

modal volume put sinhala-xtts-si-female \
  /path/to/xtts_si_female/model.pth       xtts_si_female/model.pth
modal volume put sinhala-xtts-si-female \
  /path/to/xtts_si_female/vocab.json      xtts_si_female/vocab.json
modal volume put sinhala-xtts-si-female \
  /path/to/xtts_si_female/config.json     xtts_si_female/config.json
modal volume put sinhala-xtts-si-female \
  /path/to/xtts_si_female/reference.wav   xtts_si_female/reference.wav
modal volume put sinhala-xtts-si-female \
  /path/to/xtts_si_female/sinhala_text.py xtts_si_female/sinhala_text.py
```

All five files, together. The tokenizer must match the checkpoint and the
speaker reference is not optional; a partial upload fails at load rather than
degrading quietly, which is the intended behaviour.

Then confirm what actually landed against the manifest's checksums:

```bash
modal volume ls sinhala-xtts-si-female xtts_si_female
```

The expected sizes and SHA-256 values are in
[`docs/model-inference-manifest.md`](../../../docs/model-inference-manifest.md).
A deployment must be able to say which artifact it loaded; sizes that do not
match mean the upload is not the artifact that was measured.

### 2. Deploy and verify

```bash
modal deploy services/tts/deploy/modal_app.py
modal run    services/tts/deploy/modal_app.py
```

`modal run` calls the `verify` entrypoint: it reports the cold-start time, then
synthesises every regression sentence, decodes the WAV that actually crossed the
wire, and runs the standard audio checks over it.

It checks the returned bytes rather than the array inside the container on
purpose. A well-formed WAV can still contain silence, and the encode step is
where a sample rate or a channel count gets lost.

## The numbers to record on that first run

None of these exist yet, and the inference manifest lists all of them under
"Not yet established":

| | Why it matters |
| --- | --- |
| **Cold start** | Load was 68 s on CPU. Scale-to-zero pays it on the first request after idle. |
| **Real-time factor** | 3.3–3.8× on CPU. The GPU figure decides whether live synthesis is possible at all. |
| **Peak VRAM** | 2.34 GB of system RAM on CPU. VRAM is a different number. |
| **Whether the pins work** | They were measured on Windows with Python 3.13, and CLAUDE.md forbids trusting pins across environments untested. |

Put them in the manifest when you have them. Until then, no GPU claim about this
system is true.

## Settings that trade money against waiting

| Variable | Default | What it does |
| --- | --- | --- |
| `SINHALA_TTS_MODAL_GPU` | `A10G` | XTTS-v2 is small; the constraint is latency, not capacity. Try a cheaper card before a faster one. |
| `SINHALA_TTS_MODAL_SCALEDOWN` | `300` | Seconds a container stays warm after its last request. |
| `SINHALA_TTS_MODAL_MAX_CONTAINERS` | `4` | Ceiling on simultaneous GPUs, so a burst cannot open an unbounded number. |

`SCALEDOWN` is the important one. Every second is paid for, and every second
saved is a reader who does not wait through a cold load. Set it from measured
usage — students revising in the evening look nothing like a demo.

## Cold start, honestly

A 5.6 GB checkpoint that took 68 s to load, and a target of a first segment
within 5 seconds, cannot both be satisfied by a container that starts from
nothing. Three approaches, not mutually exclusive:

**Pre-render.** The strongest answer for shared textbooks. A book is fixed;
generate its audio once, store it, and every reader afterwards gets a cache hit
in milliseconds. The cold start stops being on anyone's critical path, and GPU
time becomes a one-off cost per book rather than a cost per reader. The caching
design in `services/api` already assumes this shape.

**Keep one container warm** during the hours people actually read
(`min_containers`). Costs money for idle time; buys a predictable first
response.

**Memory snapshotting.** Modal can snapshot a container after start-up and
restore from it. Whether it helps a CUDA model, and how, needs checking against
current Modal documentation — the API and its GPU support have both moved, and
this repository has not tested it.

What none of them fix: a reader uploading their **own** PDF still waits for
first synthesis. That is where the 5-second target genuinely bites, and it is a
product decision — probably making the *first* segment of a request short —
rather than a hardware one. A full-length 250-character segment is about 16 s of
audio, so even a very fast GPU has limited room.

## What this does not change

**The licence.** XTTS-v2 weights are published under CPML, which is
non-commercial, and fine-tuning does not automatically clear it. Hosting the
voice on a public website is publishing it. Running on Modal rather than a VM
makes no difference to this, and it is unresolved.

**Permission for the speaker reference.** Also unresolved, and also required
before public release.
