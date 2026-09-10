# services/api

The reader API: upload a Sinhala PDF, get its segments, hear them, stop, and
come back to where you were.

This is the spine CLAUDE.md's step 3 asks for — digital PDF → selected page →
audio → pause and resume — with the parts that do not exist yet **named rather
than faked**.

## Three rules that run through every route

**Ownership is the store's job, not the route's.** Every read takes an owner and
returns nothing for anyone else's document, so a forgotten check is a missing
argument rather than a silent leak.

**A missing document and someone else's document look identical.** Both are 404.
A 403 on an id that exists confirms it exists, and these are private books
belonging to identifiable students.

**Placeholder audio announces itself.** Every audio response carries
`X-Reader-Real-Model`, and the manifest carries `real_model`. A listener cannot
tell a tone from speech they were not expecting, so the answer travels with the
audio rather than being available on request.

## Endpoints

| | |
| --- | --- |
| `POST /documents` | Upload a PDF. Returns **202** with a job, never waits for preparation. |
| `GET /documents` | Your documents. |
| `GET /documents/{id}` | Status, page and segment counts, and what the book lost. |
| `DELETE /documents/{id}` | The upload **and everything derived from it**. |
| `GET /documents/{id}/jobs/{job_id}` | queued, running, succeeded, failed, cancelled. |
| `GET /documents/{id}/pages/{n}` | A page's segments, and what could not be read. |
| `GET /documents/{id}/segments/{sid}` | One segment. |
| `GET /documents/{id}/segments/{sid}/audio` | WAV, generated on demand then cached. |
| `GET /documents/{id}/segments/{sid}/audio/manifest` | What produced it, without downloading it. |
| `PUT`/`GET /documents/{id}/progress` | Where the reader is, against the version they read. |
| `GET /health`, `GET /readiness` | Liveness and model readiness, answered separately. |

## Run it

```bash
cd services/api
python -m pip install "fastapi>=0.115" "python-multipart>=0.0.9" "uvicorn" \
  "pdfplumber>=0.11.4" "numpy>=1.26" "pytest>=8" "httpx>=0.27" "ruff==0.15.20"

SINHALA_READER_AUTH=development \
SINHALA_READER_ORIGINS=http://localhost:3000 \
PYTHONPATH="src:../worker/src:../tts/src" \
  python -m uvicorn sinhala_reader.app:app --reload
```

`SINHALA_READER_ORIGINS` names the origins a **browser** may call this API from
— [`apps/web`](../../apps/web) in development. It is unset by default, which
means no browser may call it at all: like the identity check it fails closed,
and `GET /readiness` reports both an empty setting and a wildcard as
limitations. `X-Reader-Real-Model` is exposed explicitly, because cross-origin
JavaScript cannot read a response header the server has not named — and if that
one is missed, the reader hears a tone with no way to know it was not speech.

Then `http://127.0.0.1:8000/docs`. Every request needs an identity header:

```bash
curl -H 'X-Reader-User: me' -F file=@book.pdf http://127.0.0.1:8000/documents
```

Tests need no environment: `python -m pytest`.

### Choosing a voice

| | |
| --- | --- |
| `SINHALA_READER_TTS` | `development` (default) or `xtts`. |
| `SINHALA_READER_TTS_DEVICE` | `cpu` or `cuda`, for the real voice. Unset means choose. |
| `SINHALA_TTS_MODEL_DIR` | Where the bundle is. The TTS package's own setting, not restated here. |

```bash
SINHALA_READER_AUTH=development \
SINHALA_READER_TTS=xtts \
SINHALA_READER_TTS_DEVICE=cpu \
SINHALA_TTS_MODEL_DIR=/path/to/xtts_si_female \
PYTHONPATH="src:../worker/src:../tts/src" \
  python -m uvicorn sinhala_reader.app:app
```

The default is the placeholder, and that is a **safe** default rather than a
timid one: a tone carries `is_real_model=false` through the header, the
manifest, readiness and the cache key, so it can never be mistaken for
narration. Defaulting the other way would make every test run, every CI job and
every `--reload` try to load 5.6 GB from a path that usually is not there.

An unrecognised value **stops the process**. CLAUDE.md forbids silently falling
back to another voice, and a typo in a deployment variable must not quietly
serve tones to a reader who was promised speech.

The checkpoint loads in a background thread at start-up, not inside the first
request — it takes over a minute, and a reader who presses play and waits that
long has been failed whatever happens next. While it loads, `GET /readiness`
reports a cold start; if it fails, readiness names the reason. Neither blocks:
`model_version` is only read once the model is actually serving, because
reading it earlier *causes* the load, and a health probe that blocks for ninety
seconds gets killed and reported as an outage.

A request that arrives mid-load still waits for it — the adapter serialises on
its load lock. The interface has no cold-start state yet, so that wait looks
like a stall. That is the next increment.

## Measured on a real book

A 168-page Grade 11 Sinhala history textbook, through the API:

```
upload + prepare   28.4s   →  168 pages, 2,829 segments
page 152                      accepted, 26 segments
first audio        39 ms      (development adapter)
same audio cached   7 ms
```

The 39 ms is a placeholder tone, not the model. It is the API's own overhead,
not a synthesis latency, and says nothing about the 5-second first-segment
target in CLAUDE.md — that has to be measured against the real checkpoint on
declared hardware.

## What stands in for something real, and what it costs

Each of these is a deliberate stopgap with the real thing named. None of them is
hidden: `GET /readiness` lists every one as a limitation, so a deployment cannot
mistake this for production.

| Stopgap | Real thing | What it costs |
| --- | --- | --- |
| Trusted `X-Reader-User` header | Accounts and verified sessions | **Anyone can claim to be anyone.** The API refuses to start serving unless `SINHALA_READER_AUTH=development` is set explicitly, so a deployment that forgets fails closed. |
| `InMemoryStore` | PostgreSQL, object storage | Documents, audio and positions are lost on restart. |
| A thread per job | Celery and Redis | In-flight work is lost on restart; no retries, no cross-process queue. |
| `DevelopmentAdapter` **by default** | The XTTS checkpoint on a GPU | Audio is a 440 Hz tone. Marked `is_real_model=false` everywhere, including in the cache key, so a tone can never be served as narration. `SINHALA_READER_TTS=xtts` selects the real voice instead. |
| An origin list in an environment variable | Origins tied to a deployment configuration | A wildcard plus header identity means any website can read any reader's documents. `/readiness` says so when one is set. |

The **shape** is what matters and is not a stopgap: ownership runs through the
store, job states are the ones CLAUDE.md names, and cache identity is the
adapter's full key. Swapping any row above touches one file.

## Caching

The cache key comes from the adapter and includes the text, document version,
model version, normaliser version, voice, settings, and whether the model was
real. Nothing here shortens it.

`TtsAdapter.cache_key` computes that key **without generating anything**, which
is what makes the common case — audio already generated — cost a dictionary
lookup. It is asserted to equal the key `synthesize` actually produces.

Concurrent requests for the same segment are deduplicated: prefetch and playback
ask for the same audio constantly, and without this the second caller starts a
second GPU job for a result the first is already producing.

## Not implemented

Bookmarks, chapter downloads, questions and answers, and the accessibility smoke
test. Audio is generated per segment on demand; a job that renders a whole
chapter ahead of time is the next thing the reader will want.

The interface now exists — [`apps/web`](../../apps/web) — but **no testing with
assistive technology has been done against it**. CLAUDE.md treats inability to
upload, play, pause, navigate or resume with assistive technology as a release
blocker, and that is a claim only a real screen reader in front of a real person
can settle.
