# What remains before Swara can ship

**As of 2 October 2026.** This is the team's to-do list for getting Swara from "works on
our machines" to a pilot with a real class. It pulls together what is spread across
[`product-plan.md`](product-plan.md), [`ui-audit.md`](ui-audit.md),
[`upgrade-roadmap-50-commits.md`](upgrade-roadmap-50-commits.md), the README's status
table and the open GitHub issues.

**How to use it.** Pick an item. Put your GitHub name in its **Owner** cell in a PR, or
comment on the linked issue, so two people don't take the same thing. Branch as
`feat/…`, `fix/…` or `docs/…`, and follow [`CLAUDE.md`](../CLAUDE.md): it governs
where this file and the plan disagree. When you finish an item, delete it here in the
same PR.

---

## Where things stand

**Working end to end:**

- **Books in.** Upload a PDF, DOCX, PNG or JPEG. FM-Abhaya legacy text is decoded, and
  scanned pages fall back to OCR.
- **Listening.** Sentence by sentence, with chapters, bookmarks and saved progress.
- **Asking.** Cited study answers, which abstain when the book has no answer.
- **Accounts and classes.**
  - Cookie sessions, roles, and recovery codes.
  - Classes, publishing a book to a class, and pre-rendering its audio.
- **Practising and tracking.** Fill-in-the-blank and model-drafted practice questions,
  progress, and spaced review.
- **Reader additions.** Pasted text, in-book search, problem reports, and offline
  chapters.
- **The interface.** A public portal, an English interface option (Sinhala is the
  default), dark mode, and a new icon.

**Not done.** Nothing has been deployed. No screen-reader user has tested anything. No
evaluation has been run. Most of what follows is release work, not features.

---

## 1. Release blockers that need people, not code

CLAUDE.md treats these as release gates. Nobody can merge their way past them.

| # | What | Why it blocks | Issue | Owner |
| --- | --- | --- | --- | --- |
| 1.1 | **NVDA pass** on Windows: sign in, upload, play, pause, navigate, resume, ask, take a quiz | "Inability to upload, play, pause, navigate, or resume with assistive technology" is a release blocker. Every phase gate in the plan asks for this pass, and none has been done | [#25](https://github.com/DSEgrp18/Web-Page/issues/25) | — |
| 1.2 | **TalkBack pass** on a cheap Android phone: the same tasks, plus offline chapters | As above | [#26](https://github.com/DSEgrp18/Web-Page/issues/26) | — |
| 1.3 | **Native-speaker review** of every Sinhala string in `apps/web/src/lib/strings.ts` and `content.ts` | Nobody fluent has read the interface yet. Newest strings, unreviewed: `settingsLanguage`, `settingsLanguageHelp`, `draftTranslation`, `restorePanel`, `assistantResize`, `assistantWidthValue`, `processingQuiz`, and the `practice…`/`quizKinds`/`quizScope…` strings on the practice branch | [#27](https://github.com/DSEgrp18/Web-Page/issues/27) | — |
| 1.4 | **Review of the English translation**, especially the privacy notice, terms and accessibility statement (`content.en.ts`, marked as drafts) | They are shown to users as drafts | — | — |
| 1.5 | **Legal review** of the privacy notice and terms, and of **guardian consent**, since students may be minors | CLAUDE.md: no pilot without it | — | — |
| 1.6 | **The voice's licence** (XTTS-v2 is non-commercial only) and **permission for the speaker recording** `reference.wav` | Has to be settled before any public release | — | — |
| 1.7 | **Ethics approval** for the user study. The consent and assent forms in `evaluation/ethics/` are drafts | No study, and so no measured release targets, without it | [#92](https://github.com/DSEgrp18/Web-Page/issues/92) | — |
| 1.8 | **Hosting decision:** where it runs, the budget, a GPU provider for the voice, and a domain | Section 4 waits on it | [#93](https://github.com/DSEgrp18/Web-Page/issues/93) | — |

---

## 2. In progress: better practice questions

Branch `feat/better-practice-questions`, owned by @heshannethmina. Students said the
questions were poor, and they were.

**Done and pushed:**

- Fill-in-the-blank asks about a recurring key term. Its options are real words the
  book uses more than once, and it skips sentences that depend on the one before.
- Gemini drafting is better (prompt v2):
  - It is asked for a kind of question.
  - It sees the neighbouring passages and the lesson's key terms.
  - Its evidence can be up to 3 sentences.
  - Its budget grows with the number of questions asked for.
- The API takes the pages, topic, kind and number of questions a student asks for.
- The privacy notice and `/readiness` say when questions go to Gemini.
- The rule that the correct answer must appear word for word in the book is unchanged,
  by decision.

**Still to do on that branch:**

- [ ] The "What to practise" form on the Practice screen. It is written but doesn't
      compile yet.
- [ ] The fake API and the web tests for the form.
- [ ] Regenerate the contract schema and run `npm run verify:contract`.
- [ ] Open the PR.
- [ ] **Rebuild the API/worker image.** The running image was built without
      `langgraph`, so model drafting can't run in Docker.
- [ ] Then set `SINHALA_READER_QUIZ=graph`. It must be set in the shell or in
      `environment:`, because compose's `environment:` overrides the root `.env`.

---

## 3. Engineering: high priority

| # | What | Detail | Where | Owner |
| --- | --- | --- | --- | --- |
| 3.1 | **The API runs out of memory loading the real voice** (audit E1) | Addressed: fp16 load on CPU, PDF worker no longer loads XTTS, voice-worker only. Measure RSS on the audit host after rebuild. | `services/tts`, `infra/` | this PR |
| 3.2 | **Garbled PDFs are accepted and read aloud** (audit F08) | Addressed: NULs and repeated clusters → `undecodable` (`note:garbled_native`), OCR `broken` can replace them. | `pdf_extract.py` | this PR |
| 3.3 | **Production must refuse unsafe defaults** | Addressed: `SINHALA_READER_ENV=production` fails closed without sessions, Postgres, Celery, Redis limits. Compose sets it on the API. | `services/api` | this PR |
| 3.4 | **Focus is lost after navigation** (F42) | Addressed in code (`RouteFocus`). Still needs an NVDA pass on sign-in and delete-class. | `apps/web` | this PR |
| 3.5 | **Reviewing a flagged page** (F25) | Addressed: `?page=` on the reader; radios draft; Save commits. NVDA on the share screen still needed. | `ShareBook.tsx`, reader | this PR |
| 3.6 | **Pipeline notes are English inside a Sinhala page** (F07) | Addressed: codes from the worker, translated in both UI languages. Old English prose still falls back with `lang="en"`. | worker + web | this PR |
| 3.7 | **Docker images are out of date** | Rebuild checklist is in `infra/README.md`. Images themselves are not rebuilt in CI from this PR; run `.\refresh` on the host. | `infra/` | this PR |
| 3.8 | **Phase 7 tidy-up** | `--font-display-face` so Abhaya Libre applies (headings restyle). `next/font/google` already self-hosts at runtime. TTS Dockerfile installs torch before copying constraints. | `apps/web`, `infra/` | this PR |
| 3.9 | **Book illustration halo in dark mode** | Dark theme uses `mix-blend-mode: multiply` so the white fringe of `swara-book.webp` takes the page colour. Re-export of the webp still optional. | `globals.css` | this PR |

---

## 4. Release track (quality-track items 43–50)

None of these is started unless noted. They run in roughly this order.

| # | Item | State | Owner |
| --- | --- | --- | --- |
| 43 | Move documents and audio to **private object storage**, with expiring access | Not started; audio lives in Postgres | — |
| 44 | **Complete deletion and retention** | Document and account deletion exist and are tested. The backup retention period is not written down, and the privacy notice promises it | — |
| 45 | **Quotas and abuse controls** | Upload limits and rate limits exist. Per-user quotas (books, pages, synthesis, model calls) don't | — |
| 46 | **Package model serving for staging**: pinned GPU/CPU images, mounted model | The Modal worker in `services/tts/deploy` is written but has **never run**; the voice has never run on a GPU | — |
| 47 | **Staging environment**: HTTPS, Postgres, Redis, worker, voice | Waits on 1.8 | — |
| 48 | **Observability**: structured logs, request and job IDs, latency, GPU, cost | Readiness exists; the rest doesn't | — |
| 49 | **Load, failure, backup and rollback tests** | Not started | — |
| 50 | **Release candidate**: full CI, browser matrix, assistive-technology results, a rehearsed rollback | Waits on everything above | — |

---

## 5. Planned features (section shipped; evaluation data still pending)

| What | Status |
| --- | --- |
| **Dense and hybrid retrieval** vs lexical | `SINHALA_READER_RETRIEVAL` (`lexical`, `dense`, `hybrid`); `swara_eval retrieval --compare` |
| **Answer evaluation** (roadmap 40) | `swara_eval answers` (citation, correctness, abstention); needs CSV under `evaluation/data/` |
| **OCR teacher correction** | `POST …/pages/{n}/correction`, reader form on `needs_review` pages, version bump |
| **Quiz results** (F34) | Results table + **Hear the question** on the practice finish screen |
| **Voice cold-start notice** | Reader polls `/readiness`; warming banner distinct from placeholder tone |
| **Grounded summaries** | `POST …/summary` (study mode, labelled `generated`, retrieval-backed) |

---

## 6. Evaluation and the user study (Phase 6)

The kit is in `evaluation/`: the protocol, rubrics, draft consent forms, and runners
for RQ1–RQ4. **No result has been measured.** Order:

1. Ethics approval (1.7).
2. Build the held-out sets. CLAUDE.md gives planning sizes: 300–500 sentences, 50–100
   transcribed pages, and 150–250 questions with unanswerable ones. Split by book.
3. Run RQ1, the verifier ablation, rated blind by teachers.
4. Run RQ4 (pre-rendering against on-demand) on a declared cheap phone.
5. Run the formative study, RQ3, with blind and low-vision students.

Only aggregate results are committed; `scripts/verify-repo-hygiene.sh` enforces this.

---

## 7. Smaller fixes (from the UI audit)

| ID | Status |
| --- | --- |
| F33 | Report form names the book and sentence; thanks announced once (heading focus only) |
| F35 | Distinct password labels and show-password names; `aria-invalid` + `aria-describedby` on wrong password |
| F36 | Owner marks a report handled (`POST …/reports/{id}/handled`) |
| F37 | Display title strips file extensions (`titleFromFilename` / `bookTitle`) |
| F30 | `formatDateTime` uses interface month names (no `si-LK` locale dependency) |
| E5 | [`docs/runbook.md`](runbook.md) + readiness limitation when OCR runs in the worker |
| — | Unavailable (offline) panel links to `/offline` |

---

## 8. Decisions needed (owner: @heshannethmina, with the team)

- **What "ship" means.** A pilot with one class on staging needs sections 1.1–1.3, 2,
  3 and 4. A public release needs everything, including 1.5–1.6.
- **F24.** "Report a barrier" links to GitHub Issues, which is English and needs an
  account. What should it link to instead?
- **F26.** Removing a class member happens at once, with no confirmation. Should it
  ask first?
- **F32.** Making a new class code retires the old one at once, with no warning.
  Should it warn first?
- **F41.** Pressing a sentence while paused resumes playback. Keep that?
- **Line height.** Should 1.9 apply to all Sinhala text, or only reading text (as now)?
- **Heading font (3.8).** Accept the restyle when `--font-display` is fixed?

---

## 9. Housekeeping

- **Close the epics that are built,** after checking each exit gate in
  `product-plan.md` §4. The NVDA/TalkBack part of each gate stays open under 1.1 and
  1.2.
  - [#81](https://github.com/DSEgrp18/Web-Page/issues/81) and
    [#82](https://github.com/DSEgrp18/Web-Page/issues/82): Phase 0.
  - [#83](https://github.com/DSEgrp18/Web-Page/issues/83): accounts.
  - [#84](https://github.com/DSEgrp18/Web-Page/issues/84): the portal.
  - [#85](https://github.com/DSEgrp18/Web-Page/issues/85): the class library.
  - [#86](https://github.com/DSEgrp18/Web-Page/issues/86): pre-rendering.
  - [#87](https://github.com/DSEgrp18/Web-Page/issues/87) and
    [#88](https://github.com/DSEgrp18/Web-Page/issues/88): practice.
  - [#89](https://github.com/DSEgrp18/Web-Page/issues/89): tracking.
  - [#90](https://github.com/DSEgrp18/Web-Page/issues/90): reader additions.
  - [#91](https://github.com/DSEgrp18/Web-Page/issues/91): offline download.
- **Check and close the older task issues** that look done:
  - [#30](https://github.com/DSEgrp18/Web-Page/issues/30): reading settings.
  - [#32](https://github.com/DSEgrp18/Web-Page/issues/32): offline download.
  - [#33](https://github.com/DSEgrp18/Web-Page/issues/33): player controls.
  - [#38](https://github.com/DSEgrp18/Web-Page/issues/38): error states.
  - [#106](https://github.com/DSEgrp18/Web-Page/issues/106): bookmarks layout.
- **The README's status table is out of date.** For example, it still lists the
  settings screen and offline downloads as open issues.

---

## Before you open a pull request

From `apps/web`:

```bash
npm run lint && npm run typecheck && npx vitest run
```

Also run `node scripts/verify-css.mjs` and `npm run verify:contract`. Judge vitest by
its exit code and any "Unhandled Errors", not the pass count.

From `services/api` and `services/worker`:

```bash
python -m ruff check src tests && python -m pytest
```

For anything visible, also run the browser tests (`browser-tests/`, both themes), and
attach screenshots at 360 px and 1280 px in light and dark.

Never commit `.env`, `models/`, PDFs, audio, `evaluation/data/`,
`services/tts/deploy/upload_bundle.py` or `.claude/launch.json`. Don't rebuild Docker
images casually: a rebuild can download gigabytes.
