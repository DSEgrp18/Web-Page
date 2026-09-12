# infra

The whole reader, in one command.

```bash
docker compose -f infra/docker-compose.yml up --build
```

Then the interface is on <http://localhost:3000> and the API on
<http://127.0.0.1:8000>. `Ctrl+C` stops it; `docker compose -f
infra/docker-compose.yml down` removes the containers, and `down -v` also
removes the database.

| | |
| --- | --- |
| `web` | The reader interface, a production Next.js build |
| `api` | Upload, segments, audio, progress, bookmarks |
| `worker` | Celery: extraction and preparation |
| `postgres` | Documents, audio, progress, bookmarks |
| `redis` | The queue |

## Why this exists, beyond convenience

Run by hand, the API defaults to in-memory storage and a thread per job, and
those defaults are what nearly every local test has exercised. This runs the
configuration a deployment would actually use: a real database, a real queue,
and preparation happening **in another process**.

That last one is the point. A job that runs on a thread shares memory with the
request that started it, and a surprising amount of code can be wrong in a way
that only shows up once it cannot. Those failures should happen here rather than
to a reader.

## The voice

By default the voice is a **placeholder tone**, and every layer says so — the
audio response header, the manifest, and `GET /readiness`.

The real voice needs two things this file cannot provide: the model bundle,
which is 5.6 GB and is delivered out of band, and `torch` with `coqui-tts`,
which are not installed in the image because they are several gigabytes for a
voice that cannot run without the bundle anyway.

`.dockerignore` excludes `models/` deliberately. Weights are **mounted**, never
built in: an image containing them could be pushed to a registry, and the
licence position of the XTTS-v2 weights under CPML is unresolved.

[`tts.Dockerfile`](tts.Dockerfile) installs torch and coqui-tts, and
[`compose.voice.yml`](compose.voice.yml) mounts the bundle:

```bash
MODEL_DIR="/path/to/folder/containing/xtts_si_female"   docker compose -f infra/docker-compose.yml -f infra/compose.voice.yml up --build
```

`MODEL_DIR` has no default on purpose. Without it compose refuses to start and
says so, rather than mounting nothing and failing at the first synthesis.

The mount is read-only. Nothing here has any reason to write to a checkpoint.

An overlay rather than a setting because somebody without the bundle should get
a working reader and a labelled tone, not a stack that will not start.

**Built but not run.** The Dockerfile is written from what
[`docs/model-inference-manifest.md`](../docs/model-inference-manifest.md)
records — `torch` installed first and from the CPU index, `transformers`
pinned below 5, `libsndfile1` present for the reference clip — and both compose
files parse. Nobody has yet built the image or heard a sentence come out of it,
because it is several gigabytes and this machine's connection is slow. Until
somebody has, run the API outside Docker for the real voice, as
[`services/api/README.md`](../services/api/README.md) describes.

### Mixing the two

The datastores are useful on their own. Running PostgreSQL and Redis from
compose while the API runs on the host gives the real voice *and* durable
storage — which is what this repository's own development setup does:

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
```

Then point the host API at them with `SINHALA_READER_DATABASE_URL` and
`SINHALA_READER_REDIS_URL`, and run a worker beside it. On Windows that worker
needs `--pool=solo`: Celery's default prefork pool does not work there.

## Page structure

Off by default. With it on, **each page of an uploaded document is sent to
Google**, which is external processing of private material and is disclosed in
`GET /readiness`. Every response is checked character for character against the
text we extracted, and a page that differs is discarded.

```bash
SINHALA_READER_STRUCTURE=gemini GEMINI_API_KEY=... \
  docker compose -f infra/docker-compose.yml up --build
```

Compose reads a `.env` **at the repository root** as well, so a key already
there is picked up without putting it on the command line — which would put it
in your shell history.

Expect rate limits. Structure is one request per page, and a free-tier key
returns `HTTP 429` after a handful. Rate-limited pages fall back to
deterministic structure and are served normally, so a large upload can come back
with some pages structured and some not, with nothing in the interface to say
which.

## What this is not

Not a deployment. There is no TLS, no secret management, no backups, no resource
limits, and the database password is `dev` in a file in the repository. It runs
on one machine for people building the thing.

CLAUDE.md's step 7 — dashboards, quotas, rollback, load testing — is not here.

## Ports

| | |
| --- | --- |
| 3000 | the interface |
| 8000 | the API |
| 55432 | PostgreSQL, so `psql` and the test suite can reach it |
| 56379 | Redis |

The database and queue ports match what
[`CONTRIBUTING.md`](../CONTRIBUTING.md) tells contributors to run for the tests
that need a server, so this stack can stand in for those containers.
