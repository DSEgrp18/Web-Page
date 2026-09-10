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
| `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/password` | Accounts. See below. |
| `GET /auth/me` | Who am I. |
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
# development mode
curl -H 'X-Reader-User: me' -F file=@book.pdf http://127.0.0.1:8000/documents

# sessions mode
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login   -H 'Content-Type: application/json'   -d '{"email":"me@example.lk","password":"a-long-enough-password"}' | jq -r .token)
curl -H "Authorization: Bearer $TOKEN" -F file=@book.pdf http://127.0.0.1:8000/documents
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
| Trusted `X-Reader-User` header, in `development` mode | Accounts and verified sessions — **now implemented**, `SINHALA_READER_AUTH=sessions` | In `development` mode **anyone can claim to be anyone**. The API refuses to serve under no mode at all, so a deployment that forgets fails closed. |
| `InMemoryStore` **by default** | PostgreSQL, object storage | Documents, audio and positions are lost on restart. `SINHALA_READER_DATABASE_URL` selects PostgreSQL instead; audio still lives in the database rather than object storage. |
| A thread per job | Celery and Redis | In-flight work is lost on restart; no retries, no cross-process queue. |
| `DevelopmentAdapter` **by default** | The XTTS checkpoint on a GPU | Audio is a 440 Hz tone. Marked `is_real_model=false` everywhere, including in the cache key, so a tone can never be served as narration. `SINHALA_READER_TTS=xtts` selects the real voice instead. |
| An origin list in an environment variable | Origins tied to a deployment configuration | A wildcard plus header identity means any website can read any reader's documents. `/readiness` says so when one is set. |

The **shape** is what matters and is not a stopgap: ownership runs through the
store, job states are the ones CLAUDE.md names, and cache identity is the
adapter's full key. Swapping any row above touches one file.

## Signing in

Two modes, and no third. `SINHALA_READER_AUTH` picks one:

| | |
| --- | --- |
| `sessions` | Real accounts. `Authorization: Bearer <token>` from `POST /auth/login`. |
| `development` | The `X-Reader-User` header, trusted completely. **Anyone can be anyone.** |

Unset is neither and every request is refused, so a deployment that forgets
authentication fails closed and loudly rather than serving private books to
whoever asks.

**The two never overlap.** In `sessions` mode the header identifies nobody — if
both worked at once, every account would be bypassable by typing a user id into
a header, and nothing about the server would look wrong. There is a test for
exactly that.

`development` stays because the whole reader interface and document pipeline can
be built and reviewed without accounts, and because checking a focus order
should not require a database and a registered user.

| | |
| --- | --- |
| `POST /auth/register` | Create an account, and sign in with it. |
| `POST /auth/login` | A token and when it expires. |
| `POST /auth/logout` | End this session. Idempotent. |
| `GET /auth/me` | Who am I — what a reloaded interface asks. |
| `POST /auth/password` | Change it, and end **every** session. |

### What these routes refuse to say

A login that answers "no such account" for one address and "wrong password" for
another has told an attacker which addresses have accounts. That is not abstract
here: this is a service for blind and low-vision readers, so membership of it is
information about a person's disability.

So every failed sign-in is the same status and the same body — and a login for
an unknown address still runs a full scrypt verification against a throwaway
hash, because otherwise it answers sooner and the timing says what the body
does not.

Registration is the one route that deliberately says more: it has to tell a
reader that an address is already registered. That makes addresses enumerable
*there*, which is why it needs a rate limit before this is public.

### Passwords and tokens are hashed differently, on purpose

**Passwords: scrypt**, deliberately slow. A password is low-entropy and chosen
by a person, so cost per guess is the only defence once a database leaks.
Parameters are `N=2^14, r=8, p=5` — one of OWASP's equivalent-work
configurations, chosen for its memory footprint:

```
N=2^17 r=8 p=1    895 ms   128 MB   <- the one usually quoted
N=2^14 r=8 p=5    545 ms    16 MB   <- chosen
```

Every login attempt costs that, including the failed ones. At 128 MB, eight
simultaneous attempts is a gigabyte, and refusing service to readers is a
cheaper attack than cracking anything.

**Session tokens: SHA-256**, deliberately fast. A token is 256 bits of
`secrets.token_urlsafe`; there is no dictionary to try, so a slow hash would
cost a tenth of a second on every authenticated request and buy nothing. Only
the hash is stored, so a leaked database hands over no working sessions.

Getting those two the wrong way round is the classic mistake, which is why both
are written down.

### Sessions last fourteen days

Long, deliberately. Signing in is a much heavier task with a screen reader or at
400% zoom than it is for someone who can see a form, so a short expiry taxes
exactly the readers this exists for. Sessions are revocable server-side, which
is what makes that defensible, and they renew in use so a daily reader is never
signed out mid-chapter.

### Not done

No rate limiting, no email verification, no password reset. A reader who forgets
their password cannot recover the account. `/readiness` lists all three on every
call, so "we have logins" cannot stand in for "this is safe to expose".

## Storage

Unset `SINHALA_READER_DATABASE_URL` and everything lives in a dictionary that
dies with the process. Set it and the same interface is served by PostgreSQL:

```bash
docker run -d --name reader-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=reader   -p 55432:5432 postgres:17-alpine

python -m pip install "psycopg[binary]>=3.2" "psycopg-pool>=3.2"

SINHALA_READER_AUTH=development SINHALA_READER_ORIGINS=http://localhost:3000 SINHALA_READER_DATABASE_URL=postgresql://postgres:dev@127.0.0.1:55432/reader PYTHONPATH="src:../worker/src:../tts/src"   python -m uvicorn sinhala_reader.app:app --reload
```

Migrations run at start-up, each exactly once, recorded in `schema_migrations`.
They are numbered SQL in `postgres.py` — reviewable in a pull request, and with
no migration framework standing between a reader of that file and what will
happen to the database. **Never edit a migration that has been applied
anywhere; add another.**

A URL that is set but unreachable **stops the process**. The alternative is
starting on the in-memory store, accepting a reader's book, and losing it at the
next restart while every health check said the deployment was configured for
PostgreSQL.

Three things are worth knowing about the schema:

- **Ownership is a `WHERE` clause**, never an application check, so a forgotten
  check is a syntax error rather than a silent leak.
- **Deletion is `ON DELETE CASCADE`.** CLAUDE.md requires deletion to remove
  everything derived, and an application deleting five tables in sequence can be
  interrupted between two of them. Cascading makes it a property of the schema:
  a new table that references a document is cleaned up because it references a
  document, not because somebody remembered.
- **Timestamps are text, not `timestamptz`.** The interface promises ISO-8601
  strings and a round trip through `timestamptz` normalises them. The cost is no
  date arithmetic in SQL — nothing needs it, and ordering still works because
  these are all UTC.

### Testing against a real database

Both stores are held to one suite, `tests/test_store_contract.py`, and the
routes are exercised against PostgreSQL in `tests/test_postgres_routes.py`.
Both **skip loudly** without a URL, because a silently skipped integration test
reports green for something nobody ran. CI sets the URL and then fails the job
if anything skipped.

```bash
SINHALA_READER_DATABASE_URL=postgresql://postgres:dev@127.0.0.1:55432/reader   python -m pytest
```

The route tests in `test_api.py` stay pinned to the in-memory store, so setting
that variable in a shell cannot quietly make them share one database.

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
