# Contributing

This repository holds the Sinhala Accessible Reader: a document reader and
document-grounded study assistant for blind and low-vision readers and students.
It is developed by three people. [CLAUDE.md](CLAUDE.md) is the governing
specification for scope and behaviour; this file describes how we work together
in Git and GitHub.

Read [CLAUDE.md](CLAUDE.md) before your first change. The rules below assume it.

Everyone taking part is covered by our [Code of Conduct](CODE_OF_CONDUCT.md).
Report a concern through a
[private security advisory](https://github.com/DSEgrp18/Web-Page/security/advisories/new)
or to [@heshannethmina](https://github.com/heshannethmina), not in a public
issue.

## Ground rules

- **Accessibility is the product.** If a change makes upload, playback, pause,
  navigation, or resume impossible with assistive technology, it does not ship.
  That is a blocker, not a follow-up issue.
- **Never commit** model weights, speaker reference audio, uploaded or private
  documents, generated audio, or secrets. This repository is public. CI enforces
  this, but the guard is a backstop, not permission to be careless.
- **Do not claim a check passed if you did not run it.** Say what you verified
  and what you did not. Unverified work that is honestly labelled is useful;
  work that is falsely labelled costs the team more than it saves.
- **No training or fine-tuning.** The Sinhala XTTS model is integrated for
  inference only.
- **Read mode never rewrites the document with an LLM.** AI-generated content
  belongs in Study mode and must be labelled.

## Getting set up

Four things are installable and runnable: the reader interface, the reader API,
and the two Python packages it sits on. Each has its own README with the
commands to run it; this section is only about **the checks CI will run on your
branch**, so that nothing fails after you push that could have failed before.

| | |
| --- | --- |
| [`apps/web`](apps/web) | The reader interface |
| [`services/api`](services/api) | Upload, pages, audio, progress, bookmarks, accounts |
| [`services/worker`](services/worker) | PDF extraction, FM-Abhaya decoding, segmentation |
| [`services/tts`](services/tts) | The Sinhala text front end and the synthesis adapter |

### Run what CI runs, before you push

**Every one of these is a job that can turn your pull request red.** They are
listed here in full because a check nobody documents is a check nobody runs.

From `apps/web`:

```bash
npm ci
npm run lint          # eslint, including jsx-a11y
npm run format:check  # prettier --check .
npm run typecheck     # tsc --noEmit
npm test              # vitest, including the axe accessibility smoke test
npm run build         # the production build
```

`npm run format` writes the fixes that `format:check` only reports. Formatting
is settled by [`apps/web/.prettierrc.json`](apps/web/.prettierrc.json) — in
particular `printWidth: 100`, which is wider than most editors default to. If
your editor wraps at 80, `format:check` will fail on code that is otherwise
correct. See [Editor settings](#editor-settings) below.

From `services/api`, `services/worker` or `services/tts`:

```bash
python -m pip install "ruff==0.15.20"
ruff check .
ruff format --check .   # `ruff format .` writes the fixes
python -m pytest
```

From the repository root:

```bash
scripts/verify-vendored-assets.sh   # legacy font tables match their recorded hashes
scripts/verify-repo-hygiene.sh      # no weights, audio, documents, or secrets tracked
shellcheck --severity=style scripts/*.sh
```

No `PYTHONPATH` is needed — each `pyproject.toml` puts the source directories on
the path for pytest. What you do need is that service's runtime dependencies;
its README lists them on one `pip install` line.

### The tests that need a server

`services/api` has database and queue tests that **skip silently** without one,
and CI fails the job if they skip — so green locally does not mean green in CI
unless you run them:

```bash
docker run -d --name sinhala-pg -e POSTGRES_PASSWORD=dev -p 55432:5432 postgres:17-alpine
docker run -d --name sinhala-redis -p 56379:6379 redis:8-alpine

SINHALA_READER_DATABASE_URL=postgresql://postgres:dev@127.0.0.1:55432/postgres \
SINHALA_READER_REDIS_URL=redis://127.0.0.1:56379/0 \
  python -m pytest
```

### Editor settings

[`.vscode/settings.json.example`](.vscode/settings.json.example) has the
formatter configuration this repository expects. Copy it once:

```bash
cp .vscode/settings.json.example .vscode/settings.json
```

`.vscode/settings.json` is ignored by Git deliberately — your editor is yours —
so the example is committed and the copy is not.
[`.vscode/extensions.json`](.vscode/extensions.json) names the extensions it
depends on; VS Code offers to install them when you open the repository.

If you use another editor, the settings that matter are: format with Prettier
for TypeScript, JavaScript, JSON, CSS and Markdown; format with Ruff for Python;
and honour [`.editorconfig`](.editorconfig) for line endings and indentation.

### The model bundle

The Sinhala XTTS model bundle is **not** in this repository and is not
downloadable from it. It is delivered out of band by the project owner and
located through configuration at runtime. If you need it, ask the owner.

Without it everything still runs: the API serves a clearly labelled placeholder
tone, and `GET /readiness` says so on every call.

## Branches

`main` is the integration branch. It is protected: nobody pushes to it
directly, including the owner.

Work happens on short-lived branches cut from an up-to-date `main`:

| Prefix   | Use                                          | Example                        |
| -------- | -------------------------------------------- | ------------------------------ |
| `feat/`  | New user-visible capability                  | `feat/12-sentence-navigation`  |
| `fix/`   | Correcting broken behaviour                  | `fix/34-resume-offset`         |
| `chore/` | Tooling, dependencies, repository plumbing   | `chore/repo-governance`        |
| `docs/`  | Documentation only                           | `docs/inference-manifest`      |
| `test/`  | Tests only                                   | `test/extraction-fixtures`     |
| `ci/`    | Workflow and pipeline changes                | `ci/postgres-integration`      |

Use `<prefix>/<issue-number>-<topic>` when an issue exists, and
`<prefix>/<topic>` when one genuinely does not. Delete the branch after merge.

```bash
git switch main && git pull
git switch -c feat/12-sentence-navigation
```

## Commits

Write commits that explain the change to someone who was not in the room.

- Use a `type: summary` subject in the imperative mood, under ~72 characters:
  `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`, `perf:`.
- Use the body for **why**, not a restatement of the diff.
- One coherent change per commit. Do not batch unrelated edits.
- Commits are authored by the human responsible for the work. Do not add
  AI-generated-by or co-authored-by bot trailers, and never rewrite or
  impersonate another person's authorship.

## Pull requests

1. Open a **draft** pull request after your first useful commit. Do not wait
   until the work is finished; early visibility is cheaper than late surprise.
2. Keep pushing small commits to that pull request.
3. Fill in the template honestly, including the "Not verified" section.
4. Mark it ready for review only when the acceptance criteria are met and the
   `ci` check is green.
5. One approving review from another team member is required. Your own approval
   never counts, and approvals are dismissed automatically when you push new
   commits that change reviewed code.
6. Resolve every review conversation before merging. "Resolved" means addressed
   or explicitly agreed, not silently closed.
7. The reviewer or author merges after approval. Merging is a human decision;
   nothing merges itself.

Keep pull requests small. A 300-line pull request gets a real review; a
3,000-line one gets a rubber stamp, and rubber stamps are how accessibility
regressions reach users.

### Reviewing

Reviewing is real work, not a formality. When you review, check that:

- The acceptance criteria in the linked issue are actually met.
- Accessibility claims were tested, not assumed.
- No private content, credentials, or large artifacts are added.
- Authorization is enforced before data reaches retrieval or an LLM.
- Failure paths, retries, and cancellation behave sensibly.
- Tests would fail if the change were reverted.

Say plainly when you have not verified something. Approving means you believe
the change is correct, not that you skimmed it.

## Issues

Track bounded work in issues using the templates. Every task needs acceptance
criteria and one named owner. Ownership is divided by area, but anyone may
review anything, and cross-area review is encouraged.

Areas: frontend and accessibility; backend, API, and document processing;
inference and operations. Per-area code owners are recorded in
[.github/CODEOWNERS](.github/CODEOWNERS) as the team assigns them.

**Before your first interface issue, read
[docs/accessible-ui-guide.md](docs/accessible-ui-guide.md).** It is the whole of
the UI/UX knowledge this project needs, and it assumes no design experience.
The reader is built for people who cannot see the screen, so the rules there are
not style preferences — a change that breaks one of them makes the application
unusable rather than untidy.

## Continuous integration

Every pull request runs [CI](.github/workflows/ci.yml). The aggregate `ci` job
is the required check on `main`; it fails if any job it depends on fails, is
cancelled, or is skipped.

CI grows with the codebase. When you add code, add the checks for it in the same
pull request. Do not add a required check name for a job that does not exist,
and do not let a skipped job stand in for a passing test.

Real-model synthesis smoke tests do not run on pull requests. They run on
trusted, access-controlled GPU infrastructure before an inference release, and
their results are reported separately from fast pull-request checks.

## Security and privacy

Report vulnerabilities and private-data exposure through
[SECURITY.md](SECURITY.md), never as a public issue.
