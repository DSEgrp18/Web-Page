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

The repository currently contains project documentation, vendored legacy-font
data, and repository tooling. Application scaffolding has not landed yet, so
there is no install or run command to document. Setup instructions are added to
this file by the pull requests that introduce the tooling they describe.

What you can run today, from the repository root, using Git Bash on Windows or
any POSIX shell:

```bash
scripts/verify-vendored-assets.sh   # legacy font tables match their recorded hashes
scripts/verify-repo-hygiene.sh      # no weights, audio, documents, or secrets tracked
```

The Sinhala XTTS model bundle is **not** in this repository and is not
downloadable from it. It is delivered out of band by the project owner and
located through configuration at runtime. If you need it, ask the owner.

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
