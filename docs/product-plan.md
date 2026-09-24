# Swara product plan: from accessible reader to accessible study platform

**Status:** agreed direction, September 2026. It supersedes the phase ordering in
[`upgrade-roadmap-50-commits.md`](upgrade-roadmap-50-commits.md), which continues as the
**quality track** described in [§12](#12-the-quality-track).

**Audience:** the three of us. It is written so that any one of us can pick up a phase
without the other two in the room.

**How to use it:** each phase has a milestone on GitHub and one or more epic issues. The
epics carry the checklists. This document carries the *reasons*, which are what stop a
change from quietly undoing a decision. If code and this document disagree, fix one of
them in the same pull request.

---

## Contents

1. [Why this plan exists](#1-why-this-plan-exists)
2. [The product](#2-the-product)
3. [Principles that carry over unchanged](#3-principles-that-carry-over-unchanged)
4. [Phases at a glance](#4-phases-at-a-glance)
5. [Phase 0 — Foundation](#5-phase-0--foundation)
6. [Phase 1 — Portal and real accounts](#6-phase-1--portal-and-real-accounts)
7. [Phase 2 — Class library](#7-phase-2--class-library)
8. [Phase 3 — Practise](#8-phase-3--practise)
9. [Phase 4 — Track](#9-phase-4--track)
10. [Phase 5 — Reader additions](#10-phase-5--reader-additions)
11. [Phase 6 — Evaluation, and Phase 7 — Release](#11-phase-6--evaluation-and-phase-7--release)
12. [The quality track](#12-the-quality-track)
13. [Migrations and configuration](#13-migrations-and-configuration)
14. [Team tracks](#14-team-tracks)
15. [Risks](#15-risks)
16. [Decisions and the alternatives we rejected](#16-decisions-and-the-alternatives-we-rejected)

---

## 1. Why this plan exists

Swara works end to end. On the real 168-page Grade 11 history textbook, one upload
becomes 2,863 sentences in 65 seconds. 144 pages are accepted, 19 are recognised by
Tesseract and flagged for review, and 5 are withheld as undecodable. From there a reader
can narrate, bookmark, resume, open a chapter, and ask a question that is answered with
citations or honestly declined.

That is a working **tool**. It is not yet something a school could adopt, and it is not
yet a dissertation contribution:

- **There is no front door.** The app opens on a box that asks for a name. The `/auth`
  router in `services/api/src/sinhala_reader/accounts.py` is complete (register, login,
  logout, me, password change, scrypt, sessions), and the web client calls none of it.
- **It covers half of studying.** A student can *listen* and *ask*. They cannot *practise*
  or *see their progress*. `CLAUDE.md` already names "revision questions grounded in the
  document" as a milestone.
- **There is no teacher side.** Every student prepares and voices their own copy of the same
  book, so every one of them pays the cold start and the synthesis cost again.
- **Nothing is measured and nothing is deployed.** The research contribution is supposed to be
  *measured* system improvement, and no evaluation set exists yet.

Building this plan also surfaced defects that sit directly underneath the new features
(§5). They are fixed first.

## 2. The product

> **Swara is an accessible Sinhala study platform. A blind or low-vision student can
> listen to a textbook, ask about it, practise on it and track their progress,
> independently. A teacher can prepare a book once for the whole class.**

### The learning loop

| Step | What the student does | State today |
| --- | --- | --- |
| **Listen** | Narration, chapters, bookmarks, resume | Built |
| **Understand** | Cited answers and abstention | Built |
| **Practise** | Questions grounded in the book, with "hear the source" | Phase 3 |
| **Track** | What they have heard, how they scored, what to revise next | Phase 4 |

The teacher side (Phase 2) runs underneath the loop. A teacher checks a book's flagged pages
once, attests the right to share it, and publishes it to a class, with its audio rendered
once for everyone.

### Who it is for

The three personas from [`accessible-ui-guide.md`](accessible-ui-guide.md) remain the test
for every decision:

- **Nimali** is blind and uses NVDA on Windows.
- **Sahan** has low vision and reads at 300% zoom.
- **Tharindu** uses TalkBack on a cheap Android phone.

This plan adds a fourth person whose needs are real but secondary: a **subject or resource
teacher** who prepares books for a class and reviews questions before students see them.

## 3. Principles that carry over unchanged

Nothing in this plan relaxes any of these. Where a new feature touches one, its section says so.

- **Read mode is the document's words.** No model supplies, corrects or smooths what a reader
  hears as the book. New generated content (questions) is study-mode content: it is labelled,
  grounded and verified.
- **Verification is mandatory, not advisory.** Structure inference rejects a page over one
  altered character, and generated questions get the same treatment (§8.2).
- **The five accessibility rules** in `accessible-ui-guide.md` §2 override any design:
  - nothing plays or moves without a press;
  - every control is a real `<button>` or `<a>`;
  - polite for progress, assertive for errors;
  - focus moves on navigation, never on arrival;
  - state is never colour alone.
- **Two live regions, ever.** Both are in `Announcer.tsx`, reached through `useAnnouncer()`.
- **Every string is in `strings.ts`.** Long public prose goes in a new `content.ts` (§6.6). Both are Sinhala, and both need native-speaker review.
- **The adapter pattern** (`answers.py`, `structure.py`, `recognition.py`, `adapters.py`) is how anything configurable is chosen:
  - a `SINHALA_READER_*` variable;
  - a `MODES` tuple;
  - a default that needs no provider;
  - fatal on an unknown value;
  - `*_limitations()` fed into `/readiness`;
  - chosen once at the composition root;
  - a `test_*_selection.py`.
- **Ownership is enforced in the store**, and anything the reader may not see is *absent*
  (404), never *forbidden* (403).
- **Every derived table cascades from `documents`**, so deleting a document removes everything made from it.

## 4. Phases at a glance

```
Phase 0 Foundation ──► Phase 1 Portal + accounts ──► Phase 2 Class library ──► Phase 3b Graph quizzes + review
      │                        │                          │                              │
      │                        ├──► Phase 3a Cloze quizzes + quiz UI ────────────────────┤
      │                        ├──► Phase 5a Pasted text · 5b Search · 5c Feedback        ▼
      │                        │                                              Phase 4 Track
      └────────────────────────┴──► Phase 5d Offline download (needs 2.5 pre-render)
Phase 6 Evaluation runs from the Phase 3 freeze · Phase 7 Release
```

| Phase | Depends on | Exit gate |
| --- | --- | --- |
| **0 Foundation** | none | The rebuilt voice speaks. A Gemini-structured book survives the Celery round trip with its headings. A killed job is reaped. Browser axe runs with contrast checking in both themes. |
| **1 Portal and accounts** | 0.7, 0.8 | Cookie-authenticated accounts cannot read each other's data. CSRF tests are green. Public pages build as static. NVDA completes sign-in, register and recover. |
| **2 Class library** | 1, 0.2, 0.5 | The access matrix is green on Postgres. A student plays pre-rendered audio with no synthesis on the request path. Unpublishing revokes access immediately. |
| **3a Cloze and quiz UI** | 0.2, 1 | Verifier fixtures pass. Cloze needs no provider. NVDA completes a quiz, including "hear the source". |
| **3b Graph and teacher review** | 2, 3a | The import-isolation test is green. The bounds hold under a failing fake. Approve and publish work. |
| **4 Track** | 1 (coverage), 3a (scores), 2 (teacher view) | The dashboard carries everything as text. Consent gating tests pass. |
| **5a–5c** | 1 (5b also needs 0.10) | Per-feature tests, plus an assistive-technology check. |
| **5d Offline** | 2.5 | Offline playback on Android. Caches are cleared on sign-out. |
| **6 Evaluation** | Features frozen at the 3b gate for RQ1 | Protocol approved; data collected. |
| **7 Release** | All | Quality-track items 46–50. |

Every phase gate includes an **NVDA or TalkBack pass on the new core task**. Automated
checks show that nothing is obviously broken, not that the feature works.

---

## 5. Phase 0 — Foundation

Every item here was confirmed against the code. Several of them block the features that
follow, so they come first.

### 0.1 The voice is broken in both runtimes

**What is wrong.** `infra/tts.Dockerfile` installs `torch>=2.5`, which is a floor, not a pin.
On the rebuild of 23 September it resolved to torch 2.9. From that version coqui-tts
requires `torchcodec` for audio IO, and the voice fails at import:

```
ImportError: From Pytorch 2.9, the torchcodec library is required for audio IO
```

`services/tts/deploy/modal_app.py` pins `torch==2.9.1`, so the GPU deployment would fail
the same way on its first `modal run`. This is the failure the "What the Modal deployment
pins" section of the [inference manifest](model-inference-manifest.md) warned about, and
the reproducibility problem in #79, seen on our own machine: the same commit produced a
different, broken image.

**Fix.**
- Pin `torch==2.8.0` and `torchaudio==2.8.0` in **both** runtimes. That is the last pair before torchcodec became the audio IO path, and the manifest already records torchcodec as deliberately absent.
- Pin `coqui-tts` exactly, and keep `transformers>=4.57,<5`.
- Freeze what each image resolves into `infra/constraints/{api,tts-cpu}.txt` and install with `-c`. This closes #79 for both Python images.
- Add a build-time smoke test, `RUN python -c "from TTS.tts.models.xtts import Xtts"`, so a bad resolve fails the build rather than the first reader.
- Add a CI job that builds the image without weights and runs that import.

**Rejected:** installing torchcodec plus FFmpeg. It is heavier and reverses a decision the manifest recorded with its reasons.

**Status.** The voice fix landed first, as its own pull request: `torch==2.8.0`,
`torchaudio==2.8.0` and `coqui-tts==0.27.5` in both runtimes, an import check in
both image builds, and `.github/workflows/python-images.yml` building the Docker
image in CI whenever its Dockerfile changes. Reading the coqui-tts source showed
the cause precisely: 0.27.5 raises on import when torch is 2.9 or newer and
torchcodec is absent. Then #79 closed the rest: `infra/constraints/python.txt`,
the `pip freeze` of a known-good build, pins every package in both Python images,
and the workflow fails if either image installs a package the file does not pin.

### 0.2 Segment role and level are lost on reload

**What is wrong.** In `services/worker/src/sinhala_documents/serialise.py`, `_segment`
writes no `role` or `level`, and `_read_segment` reads none. They survive only in the
in-process `_PREPARED` cache in `preparation.py`, which holds 8 documents. Under Celery the
worker prepares a book and the API reloads it from the database. Every heading, caption and
running head then comes back as `unknown`. As a result `build_passages` finds no headings,
`section_path` is empty, and running heads leak into the passages.

The round-trip test cannot see this. `DeterministicStructure` assigns `UNKNOWN` to
everything, so there is nothing to lose. It only shows when `SINHALA_READER_STRUCTURE=gemini`.

**Fix.** Add optional `role` and `level` keys, and read them with `.get()` defaults. This
needs **no format bump**: it is the same backward-compatible pattern the file already uses
for `chapters`. Old rows read as `UNKNOWN`, which is what they effectively were. Test with a
fake `StructureAdapter` that assigns HEADING and CAPTION, round-trips through the store, and
asserts a non-empty `section_path` from `build_passages`.

### 0.3 The voice never receives the role-aware text

**What is wrong.** `app.py`'s audio route synthesises from `segment.display_text`, and the
manifest route computes its key from the same field. The pipeline builds `spoken_text` and
`model_text` using `number_style_for(block.role)` (in `structure.py`), so that "1.1" in a
heading is read as a section number rather than a decimal. Those stored fields never reach
the voice, because the adapter runs its own normalisation again without a role.

**Fix 0.2 alone would change nothing a reader hears.** Synthesise from the stored
`spoken_text` and `model_text`, and key the cache on them.

**This invalidates almost nothing.** Both the adapter's normaliser and
`number_style_for` default to `NumberStyle.PROSE`, so for an ordinary segment the stored
text *is* what the adapter would have derived: every cache key stays the same. Only
headings, captions, contents rows, addresses and page numbers read digits as identifiers.
Those roles exist only when structure inference is on, so only those segments that
contain digits get new keys. Those are exactly the clips that were read wrongly.

### 0.4 Structure is missing from the document version

**What is wrong.** `pipeline._document_version()` hashes the source, the pipeline, the
converter, the normaliser and the OCR mode, but not the structure adapter. `CLAUDE.md`
requires structure provenance "in the document version and in every affected cache key".
At the moment, turning structure on leaves stale audio in the cache.

**Fix.** Append `structure=<adapter version>` only when the adapter is not deterministic.
OCR uses the same trick, so every existing document keeps its version and its audio.

### 0.5 The audio cache fails for a second reader

**What is wrong.** In `postgres.py` the `audio` table's primary key is `cache_key` alone.
Inserts are `ON CONFLICT (cache_key) DO NOTHING`, and `get_audio` filters by `owner`. The
key depends on text and document version, not on the reader. So when two readers upload
the same PDF, the second reader's clip is discarded, and it is synthesised again on every
play. For a class library, where many students read one teacher's book, this is the main path.

**Fix.** Migration `0006` makes the primary key `(document_id, cache_key)`. Existing rows
stay unique.

### 0.6 Jobs that outlive their process

**What is wrong.** A preparation job stayed `running` from 15 to 23 September, because the
process doing it had died and nothing notices that. The interface kept saying "being
prepared" for eight days. Pre-render and quiz jobs are longer, so this gets worse.

**Fix** (`0007`, landed).
- A running job holds `jobs.lease_expires_at` (120 s). A heartbeat thread in the
  preparing process renews it every 30 s. It is a thread rather than a callback
  from the pipeline because the event to detect is the process dying, and the
  thread dies with it.
- A reaper fails any running job whose lease has passed, at stage `stalled`, with
  a detail telling the reader what happened and what to do. It runs in the API
  at start-up and every 60 s, in thread and queue mode alike, and it is one
  idempotent statement, so several processes may reap at once. A job started
  before leases existed gets the same 120 s grace from its last update.
- A heartbeat can never revive a job the reaper has failed: the renewal checks
  the state in the same statement.
- A transient failure renews the lease before the queue retries, so a slow
  broker cannot let the reaper fail a job that is only between attempts.

**Still to do.**
- Per-page progress ("page 12 of 168") and a retry action. Both need interface
  work, so they are a separate increment.
- The Celery visibility timeout. Today tasks are killed at 15 minutes against
  a 1-hour default, so nothing is redelivered early. It matters once pre-render
  tasks run long (Phase 2, §7.4), and is set there.

### 0.7 Every tab has the same title

No route sets a title, so every tab reads the app name. That fails WCAG 2.4.2 (Page Titled).
Each `page.tsx` exports a `metadata` title, and the reader sets the book's title
client-side, since it is private and fetched in the browser. Check with NVDA that Next's
route announcer and our focus-on-heading do not announce the page twice.

### 0.8 CSS debt

- `ConfirmDialog.tsx` uses `.confirm-dialog`, `.row` and `.danger`, which are defined nowhere. The delete confirmation renders with browser defaults, below the 48 px touch target. Switch it to the existing `.dialog`, `.dialog-actions`, `.btn-quiet` and `.btn-danger`.
- Undefined tokens are still referenced: `--space-4`, `--space-5`, `--radius-sm` and `--shadow-sm`. Map them to `--s4`, `--s5`, `--r-sm` and `--shadow-1`.
- `.btn` and `.dialog` are each defined twice, and there are three breakpoint systems. Merge the duplicates, and use one set of em-based widths (`30em`, `48em`, `64em`), because em responds to text zoom.
- Add `apps/web/scripts/verify-css.mjs` to `npm run lint`. It fails on any `var(--x)` with no definition, and on hex colours outside the token blocks.

### 0.9 Contrast is unverified

Commit `560a78d` changed the palette **and** deleted the measured ratios from the token
comments. Meanwhile `apps/web/tests/a11y.test.tsx` turns off axe's `color-contrast` rule, on
the grounds that "the measured ratios are recorded" in `globals.css`. Contrast is now
neither documented nor tested. The old figures cannot simply be restored, because the
colours they measured no longer exist.

**Fix.**
- A `tokens.contrast.test.ts` parses both themes' token blocks and asserts WCAG ratios for declared pairs:

  | Pair | Minimum |
  | --- | --- |
  | ink on paper and panel | 4.5 |
  | muted ink | 4.5 |
  | on-green on green | 4.5 |
  | status ink on wash | 4.5 |
  | edge on paper | 3 |

- The token comments are generated from that test's report, so the recorded figures are measured rather than typed.
- Add `@axe-core/playwright` to `browser-tests/` with contrast checking **on**, in real Chromium, in both themes.

### 0.10 Small clean-ups

- Delete `services/api/src/sinhala_reader/worker.py`. Compose uses `celery_worker.py`, and two entry points invite drift. (#100)
- **Do not cache passages yet; measured, and the plan was aimed at the wrong thing.**
  At the size of the real textbook (2,856 segments, 336 passages), per question:

  | Step | Median |
  | --- | --- |
  | `build_passages` | 10 ms |
  | Building the BM25 `LexicalIndex` | 54 ms |
  | One search | 0.5 ms |

  The index, not the passages, is most of the cost, and both are rebuilt on every
  question (`answerer.py`, `gemini_answers.py`). About 64 ms is invisible to someone
  who has just typed a question, and a written answer from Gemini takes seconds.

  A cache here would also be wrong later. Phase 2 withholds pages per class (§7.2), so
  a cache keyed on the document version alone would serve a withheld page to class
  members. Revisit with in-book search (5b): search-as-you-type would rebuild on every
  keystroke. Cache the **index** then, keyed on the version *and* the withheld-page
  overlay, and measure before and after.

---

## 6. Phase 1 — Portal and real accounts

### 6.1 Routes

Next route groups separate the public site from the product. They are in one app, with one
design system and one accessibility test suite.

```
src/app/
  layout.tsx            html lang="si", fonts, skip link
  (public)/             statically rendered, no API providers
    page.tsx            /                landing
    how-it-works/  for-teachers/  help/  accessibility/  privacy/  terms/
    sign-in/  register/  recover/  join/[code]/
  (app)/                session provider, announcer, app shell
    library/                         /library
    library/[id]/                    /library/[id]        the reader
    library/[id]/practise/[quizId]/  a quiz
    progress/  review/  bookmarks/  classes/  account/  offline/
    teach/ …                         teacher screens
  api/[...path]/route.ts             the same-origin pass-through (6.2)
```

- **A signed-in visitor to `/` is redirected to `/library` before render.** This keeps the rule `Library.tsx` states in its own header, that a returning reader should never have to scroll past a marketing page. The welcome strip stays in the library for new readers.
- **Old URLs:** `/documents/:id` gets a 308 redirect to `/library/:id`, with `?segment=` kept, so bookmark links keep working.
- **`/documents/[id]/study` is deleted.** Nothing links to it since `AssistantDrawer` replaced it. Its test coverage moves to the drawer. (Done: the route redirects to the book, and the drawer's tests now cover cited sentences and abstention.)

### 6.2 Sessions: an httpOnly cookie through a same-origin pass-through

| | localStorage bearer token | httpOnly cookie through a same-origin pass-through (**chosen**) |
| --- | --- | --- |
| XSS | Any script can read the token and use it from anywhere. The risk is real: pdf.js renders untrusted PDFs inside our page, and CVE-2024-4367 was arbitrary script execution in pdf.js. | Script can act only while the tab is open. The credential cannot be taken away. |
| CSRF | Not applicable | Needs mitigation (below) |
| CORS | Stays cross-origin and fragile | Gone. The browser talks only to its own origin. |
| Audio, PDFs, offline | Every request needs a header; a service worker struggles to cache authenticated requests | Plain same-origin requests |

**The pass-through** is a route handler, `app/api/[...path]/route.ts`, rather than
`rewrites()`, for three reasons:
- Rewrites are compiled at build time, which prevents promoting one image from staging to production.
- The rewrite proxy times out at 30 s, but a study answer may take 90 s.
- `proxy.ts` buffers request bodies to 10 MB, but an upload may be 200 MB.

The handler:
- reads the API address from a server-only variable at run time;
- streams bodies;
- passes an allow-list of headers, including `Range`, `Content-Range`, `Set-Cookie` and `X-Reader-Real-Model`;
- **strips any incoming `X-Reader-User` or `Authorization`**;
- times out at 120 s.

**API changes:**
- `security.py` reads the session from `__Host-swara_session` (`HttpOnly; Secure; SameSite=Lax`). It is Lax, not Strict, because Strict signs a student out when they follow a teacher's link from a messaging app.
- **CSRF.**
  - Reject `Sec-Fetch-Site` values of `cross-site` and `same-site`.
  - Require `X-CSRF-Token`, an HMAC of the session using a new `SINHALA_READER_SECRET`. The secret is fatal if it is missing or shorter than 32 bytes in sessions mode.
  - The Fetch-Metadata check also covers GET, because a GET on audio triggers synthesis, which costs money.
- `accounts.py` sets the cookie and returns the account (with its role) and the CSRF token. The token no longer appears in the body.
  - A bearer token is still accepted for tests and programmatic clients, but no route issues one to a browser.
  - Adds `POST /auth/logout-everywhere` and `DELETE /auth/account`.
- Compose switches to `SINHALA_READER_AUTH=sessions`. The header mode remains for API tests and curl only.

**The web client:**
- `identity.ts` becomes `session.ts`. Its own header anticipated this: "one function is replaced and nothing else moves."
- `ReaderApi` loses its `owner` parameter and sends the CSRF token.
- `AppFrame` splits into `PublicFrame` and `AppShell`.
- New failure kinds: `signed_out` (401) and `throttled` (429). A 503 stops meaning "identity".

### 6.3 Roles: nobody can make themselves a teacher

- Migration `0009` adds `users.role`: `student` (the default), `teacher` or `admin`.
- **Registration always creates a student.** Teachers are made in one of two ways:
  - the admin command line, `python -m sinhala_reader.admin grant-role`;
  - a single-use teacher invitation code issued by an admin.
- **An admin has no content access.** "Absent, not forbidden" applies to admins too. Admin work happens on the command line.
- An `audit_events` table records role grants, resets, publishing and approvals. It stores reason codes, never content.

### 6.4 Rate limiting

`ratelimit.py` follows the adapter pattern: `SINHALA_READER_RATE_LIMIT`, `memory` (the
default) or `redis`.

| Bucket | Limit |
| --- | --- |
| Login, per email address | 10 per 15 minutes, whether or not the account exists, so the limit reveals nothing |
| Login, per IP address | 30 per 15 minutes |
| Registration | 5 per hour |
| Recovery and reset | 10 per hour |
| Joining a class | 10 per hour |
| Questions | 60 per hour |
| Quizzes | 10 per day |
| Uploads | 30 per day |

The answer is 429 with `Retry-After`. **No CAPTCHA**, because it is inaccessible and WCAG 2.2
SC 3.3.8 applies.

### 6.5 Password recovery without email

1. **Recovery code (self-service).** A single code is shown once, at registration, with copy and "download as text" buttons. It resets the password and ends every session, and can be regenerated from the account page.
2. **Teacher reset (Phase 2, landed).** A teacher can issue a 30-minute single-use code only for an active student in *their own* class. It sits beside the student's own recovery code and never replaces it, so a teacher cannot take away a code the student kept. It changes no password until the student spends it on the recovery page with their own email address, which the teacher never sees. It is audited, and the student is told who made it, on every screen until they acknowledge it, whether or not it was used.
3. **The admin command line**, as a last resort.

### 6.6 Public pages

Long prose lives in a new `apps/web/src/lib/content.ts`, which needs native-speaker review
like `strings.ts`.

| Page | What it must say |
| --- | --- |
| `/` | What Swara is, the four-step loop, who it is for, "Create account" and "Sign in". No autoplay and no video. |
| `/how-it-works` | The two modes: read mode speaks the book's own words; study and practice content is generated, labelled and cited. |
| `/help` | Using Swara with NVDA and TalkBack, zoom and themes, how to report a problem. |
| `/for-teachers` | The class library, rights attestation, page review, question review, and what a teacher can and cannot see. |
| **`/accessibility`** (mandatory) | WCAG 2.2 AA as the target, with an honest status of "partially conformant". Known limits: OCR pages need review; equations, tables and diagrams are not described; the interface has not yet had native-speaker review (#27); the NVDA and TalkBack passes are pending (#25, #26). How to report a barrier, and the date of the last review. |
| **`/privacy`** (mandatory) | What is stored. What leaves the server and when: Google receives page text if structure inference is on, retrieved passages for written answers, and passages for graph quizzes, and not for training. Modal receives only spoken text. Retention and deletion, including backups. What teachers see, and only with consent. Guardian consent for minors. |
| `/terms` | Upload only what you have the right to use. A teacher's attestation duties. No public sharing. The XTTS licence is non-commercial. |

**Exit gate:** see [§4](#4-phases-at-a-glance). Also, `/readiness` no longer lists "trusted header" or "no rate limiting".

---

## 7. Phase 2 — Class library

### 7.1 Data model (migrations `0010` and `0011`)

- **`classes`**: an 8-digit join code (easiest on a phone keypad and with a screen reader), rotatable. Joining creates a *pending* membership that the teacher approves, which is the real defence against guessing codes.
- **`class_members`**: the membership state (`pending`, `active`, `removed`), `share_progress` (off by default) and `consented_at`.
- **`published_books`**: a **pinned version** and a **rights attestation** (basis, note, who, when). The pin is per document, so a student in two classes never sees two versions of the same book.
- **`class_books`**: the insert checks that the teacher owns the document, so a teacher can publish only their own documents.
- **`prepared_versions`**: the pinned version's payload, copied on publish, so the owner can keep working on a new version.
- **`page_reviews`**: `accepted` or `withheld`, per page, per version.

### 7.2 Authorisation in the store

**Reading** is allowed to the owner, **or** to an active member of a class the book is
published to, at the pinned version. **Writing** stays owner-only. Both return 404 otherwise.

- One store method, `Store.readable_document(document_id, reader)`, holds the predicate. It is a `UNION` of the owner's read and the class-member's read, joined through `published_books`, `class_books`, `class_members` and `classes`.
- `app.py` gains `readable()` beside `owned()`.
  - `readable()` covers pages, segments, audio, the manifest, the file, questions, search, reading quizzes, and the reader's *own* bookmarks and progress on that book.
  - `owned()` covers upload, rename, delete, jobs, publishing, pre-render and writing quizzes.
- Withheld pages are an overlay for class readers. They are absent from narration, retrieval and quizzes, and announced as "withheld by your teacher".
- **Audio:** `get_audio(cache_key, document_id, reader)` uses the same predicate. Class members read the teacher's pre-rendered rows.
  - **Private uploads of the same PDF by different students are not shared**, deliberately. A shared cache would reveal that someone else holds the same file. The class library is the sanctioned way to prepare a book once.
- `app.py`, at 820 lines, is split into `routes/*.py` in this phase.

**`tests/test_access_matrix.py` is a release gate.**
- It runs against both stores, parametrised over seven actors, three resources and every route.
  - The actors: the owning teacher, an active member, a pending member, a removed member, a member of another class, an unrelated student and an admin.
  - The resources: the teacher's unpublished book, the teacher's published book, and a student's private book.
- The expected result is 200 or 404, never 403.
- It also asserts:
  - a teacher never sees a student's bookmarks, notes or questions;
  - unpublishing and removing a member take effect on the next request;
  - deleting a published book is refused until it is unpublished, and then cascades.

### 7.3 Publishing

1. The teacher decides on each `needs_review` page: accept it, or withhold it.
2. The teacher attests the right to share, choosing a basis: public domain, government textbook, publisher permission, own work, or other with a note.
3. The teacher publishes to one or more classes. This is refused with the code `unreviewed_pages` until every flagged page has a decision.

Publishing again moves the pin and marks older quizzes stale (§8.6). Text correction itself
stays quality-track item 34.

### 7.4 Pre-render

> **Landed (#86):** `prerender.py`, `POST/GET /documents/{id}/prerender`, the
> `voice` Celery queue and the `voice-worker` Compose service, and the section on
> the share page. Progress is read from the audio cache instead of a job row, so
> it is right across processes and a stopped run resumes by starting again; the
> job table stays the preparation job's. Not yet: Opus storage (below), which
> needs an encoder dependency and a listening check against WAV, and chunked
> "current chapter first" ordering, which the cache-based resume makes less
> urgent.

- **Tasks.** `sinhala_reader.prerender_book` plans chunks of about 60 segments, current chapter first, and queues `sinhala_reader.prerender_chunk` on a Celery queue named `audio`.
  - Chunks keep each task well inside the time limit and the visibility timeout.
  - Each segment goes through `SynthesisService`, which checks the cache first, so a restarted job skips finished work.
- **Progress.** The teacher sees "412 of 3,120 sentences". It is announced politely at start, finish and failure only.
- **Workers.** Compose gets a separate `voice-worker` (the tts image, `-Q audio --concurrency=1`), because two prefork processes would each load the 5.6 GB checkpoint.
- **Cost.** On CPU the manifest measures 3.3–3.8× real time, which is **about 28 hours for one 168-page textbook**. That is workable overnight for one book, and not beyond. `SINHALA_READER_TTS=modal` adds a `ModalAdapter` that sends only spoken text, as `modal_app.py` already requires. It is blocked until the model upload to Modal succeeds.
- **Storage** (`0014`): Opus at about 24 kbps. That is about 11 MB per hour against WAV's 173 MB, which matters for downloads on Tharindu's phone. Object storage (quality-track item 43) must land before production pre-render: one book stored as WAV in the database is about 1.7 GB.

---

## 8. Phase 3 — Practise

> **Landed (#87, #88).** `sinhala_documents/quiz.py` (the verifier, with one
> rejection code per check, and the cloze generator), `quiz_graph.py` (the
> bounded LangGraph loop), `sinhala_reader/practice.py` and `routes/practice.py`,
> migration `0013_quizzes`, the `sinhala_reader.draft_quiz` Celery task, and the
> practice screen at `/library/[id]/practice`. Differences from the design below,
> each deliberate: questions are stored as one JSON document per quiz rather than
> a `quiz_questions` table, since they are made, reviewed and deleted together;
> answers are each reader's latest per question (`quiz_answers`) rather than
> attempts; the teacher's review is `draft → published`, with publishing as the
> approval of every question left in, and review removes questions but never
> edits them. `SINHALA_READER_QUIZ=graph` needs the queue: the API refuses to
> start without it, and a subprocess test proves the API never imports
> `langgraph` or `langchain_core`.

### 8.1 Two generators behind one adapter

`services/api/src/sinhala_reader/quizzes.py` follows the adapter pattern exactly.

| Mode | What it is | Needs |
| --- | --- | --- |
| **`cloze`** (default) | Fill-in-the-blank from the book's own sentences | Nothing: no provider, no key, no network |
| **`graph`** | Multiple choice drafted by Gemini, orchestrated with LangGraph | The worker, a Gemini key |

`build_quiz_generator()` is fatal on an unknown value. It is **also fatal on `graph` without
`SINHALA_READER_QUEUE=celery`**, because thread mode would import langgraph into the API
process. For `graph`, the API holds only a mode marker and never constructs the generator.

The worker code lives in `services/worker/src/sinhala_documents/quiz/`:

| Module | Holds |
| --- | --- |
| `model.py` | Questions, options, evidence, candidates, rejection codes; no framework imports |
| `verify.py` | The deterministic verifier, shared by **both** modes |
| `cloze.py` | The cloze generator |
| `graph.py` | The only module that imports `langgraph` |
| `generator.py` | The `QuizGenerator` interface |

### 8.2 The verifier: every question passes through it

The rule it enforces is written into `CLAUDE.md`: **a model may write a question; it may
never be the only judge of its answer.**

Evidence is normalised before comparison: NFC, and whitespace collapsed with
`blocks._flatten`. The **zero-width joiner and non-joiner are kept**, because they are part
of Sinhala words, and a joiner mismatch rejects the question. How often that happens is
measured in RQ1.

| Rejection code | Rejects when |
| --- | --- |
| `SCHEMA` | The candidate does not have the expected shape |
| `PASSAGE_OUT_OF_RANGE` | The cited passage number is not one that was sent |
| `EVIDENCE_PAGE_NOT_ACCEPTED` | The evidence is on a page that needs review or is withheld |
| `QUOTE_NOT_IN_PASSAGE` | The normalised quote is not a substring of the cited passage |
| `QUOTE_LENGTH` | The quote is outside 20–400 characters |
| `KEY_NOT_IN_QUOTE` | The correct option is not inside the quote. This is v1's definition of "supported": an answer is a span of its evidence, which can be checked by construction |
| `DISTRACTOR_IN_QUOTE` | A distractor appears in the quote, or in the sentence containing it |
| `DISTRACTOR_NOT_IN_SCOPE` | A distractor does not occur in the chapter, so it would not be a plausible book term |
| `OPTIONS_NOT_DISTINCT` · `OPTION_COUNT` | Options repeat after normalisation, or there are not four |
| `KEY_IN_STEM` | The answer appears in the question |
| `STEM_NOT_SINHALA` · `MARKUP` | The question is not Sinhala, or contains markup |
| `DUPLICATE` | Same evidence sentence, or same answer, as a question already accepted |
| `BLIND_CHECK_DISAGREED` | The optional model check chose a different answer |

**One failed check discards the question.** An accepted quote is mapped back to its segment
ids with `blocks.locate`. That mapping is what makes "hear the source" possible.

### 8.3 Cloze: deterministic, and good enough to ship alone

1. **Scope:** the chapter's paragraph, list-item and caption segments, on accepted pages only.
2. **Choose terms:** salient terms have a high inverse document frequency within the chapter, and appear at least twice in the whole book (a single occurrence is more likely an OCR or typing error).
   - The weighting comes from `LexicalIndex`, which gains a public `idf()`. BM25 itself is unchanged.
   - Words from `answerer._QUESTION_SCAFFOLD` are excluded. Numbers are their own type, because years make good blanks.
3. **Blank:** a term is blanked only where it occurs once in its sentence.
4. **Distractors:** three other salient terms from the same chapter, of the same type, within ±50% of the answer's length. Where possible they share its last two characters, so the Sinhala case ending matches.
5. **Order:** ties break on score, then on the term. Options are shuffled with a seed taken from the question id. The whole output is reproducible.
6. **Verification:** the evidence is the sentence itself, so cloze passes the verifier by construction. A test asserts it passes 100% of the time anyway.

### 8.4 Graph: LangGraph and Gemini, in the worker only

```
START → select_seeds → draft → verify ─┬─ failed, attempts < 2, budget left → revise → verify
                                        ├─ passed, check on  → blind_check → accept
                                        └─ passed, check off ──────────────→ accept
accept ─┬─ enough accepted · budget spent · no seeds left → END
        └─ otherwise → draft
```

| Node | Kind | Does |
| --- | --- | --- |
| `select_seeds` | Deterministic | Ranks accepted passages in scope by salient-term density |
| `draft` | One model call | Numbered, fenced passages, exactly as `gemini_answers._prompt` builds them. The system text says passages are data, never instructions. A JSON schema asks for the question, four options, the correct index, the passage number and the evidence quote. |
| `verify` | Deterministic | §8.2 |
| `revise` | One call per batch | Returns failed candidates with their rejection codes as fixed instructions |
| `blind_check` | One call (optional) | A second model sees only the passage, the question and shuffled options, and picks one. A mismatch discards the question without another revision. **It may reject a question; it may never accept one.** |
| `accept` | Deterministic | Removes duplicates, maps quotes to segments, appends the question |

**Bounds, all enforced by a single `budget_left(state)` function:**

| Bound | Limit |
| --- | --- |
| Revisions per candidate | 2 |
| Model calls per quiz | 16 |
| Draft rounds | 4 |
| Wall clock | 240 s |
| `recursion_limit` | 50, as a backstop |

- **Transport.** Reuses `gemini._post`, `ENDPOINT` and `API_KEY_ENV`, with the call injectable for tests. There are **no LangChain model wrappers**: LangGraph orchestrates, and our own code makes the calls.
- **Failure is explicit.** If the provider fails and nothing was accepted, the quiz is `failed` with the code `provider_unavailable`. The interface *offers* a fill-in-the-blank quiz as a choice. It never switches generators silently, for the same reason we never switch voices silently.
- **Provenance** is stored on every quiz: `graph/{model}+check-{model|off}/prompt-{v}/verifier-{v}/langgraph-{v}`. No passage text is written to the logs.
- **The API never imports it.** A subprocess test starts the API with `SINHALA_READER_QUIZ=graph` and asserts that no `langgraph`, `langchain_core` or `langgraph_sdk` module was loaded. `langgraph` 1.2.12 depends on `langchain-core`, so this test is what keeps "LangGraph only" true.
- **Packaging.** A worker extra, `quiz = ["langgraph==1.2.12"]`, with constraints. `api.Dockerfile` becomes multi-stage with a `worker` target, so the API image never contains langgraph and the two images share source layers and cannot drift apart.
- **The task** is `sinhala_reader.generate_quiz` on a Celery queue named `quiz`.

**Why LangGraph at all.** The loop has real structure: a bounded revise cycle, conditional
routing, a recursion backstop and per-node events. LangGraph makes that explicit, and lets
each node be switched off for the RQ1 ablation. A hand-written loop could do the same, and
the dissertation should say so.

### 8.5 Teacher review is a database status, not a paused graph

Quiz states: `generating → draft → approved → published`, plus `failed`, `stale` and
`withdrawn`. A teacher approves or rejects each question and can add a note.

LangGraph's interrupt feature was rejected for this, for five reasons:
1. It needs a persistent checkpointer, whose tables would sit outside our migrations and our cascade deletion.
2. Review happens days later and across deployments, but a paused graph's state is tied to one graph version.
3. Resuming a graph would put langgraph into the API.
4. Approval is a domain fact (who, when) that must be queryable, audited and deleted with the document.
5. The student's path must never depend on graph state.

**Personal quizzes** (a student on their own book) are usable straight away. They are
labelled either "fill-in-the-blank from the book" or "written by a model, checked by rules,
not by a teacher". **A class quiz needs a teacher's approval.**

### 8.6 Data and routes (migration `0013`)

- **Tables:**
  - `quizzes`: scope, generator, generator version, status, reason-code counts only, and approval fields.
  - `quiz_questions`: the question, options, the correct index, the evidence passage, segment ids and quote, the page, the status and provenance.
  - `quiz_attempts` and `quiz_responses`.
- **Routes:**
  - `GET`/`POST /documents/{id}/quizzes`
  - `GET /quizzes/{id}`. The correct answer is **not** sent until the question has been answered.
  - `POST /quizzes/{id}/attempts`
  - `PUT /attempts/{aid}/responses/{qid}`
  - `POST /attempts/{aid}/complete`
  - For teachers: editing a question, publishing and withdrawing.
- **Invalidation:** a new document version or a moved pin marks the quiz `stale`. Stale quizzes leave practice, but past attempts remain as history.

### 8.7 The quiz screen

- One question per screen, headed "Question 3 of 10". Focus moves to the heading only when the student presses **Next**.
- The question is a `<fieldset>`, with the question as its `<legend>` and native radio buttons for the options.
- There is an explicit **Check answer** button. **Never submit on selection**: in NVDA's focus mode the arrow keys change the selected radio button.
- Feedback is static text beside the question plus one polite `say()`. It never uses `alert()`, because a wrong answer is not an error. The result is stated in words, never by colour or an icon alone.
- **Hear the question** plays the question and options through the same voice, only when pressed.
- **Hear the source** opens the reader at the evidence segment, **cued but not playing**, through `usePlayer`'s `cue(segmentId, 0, false)`. The reader shows **Back to the quiz**. Each answer is saved as it is checked, so nothing is lost.
- **No time limits** (WCAG 2.2.1). An attempt can be resumed. No single-key shortcuts.
- The results page opens with a sentence ("You answered 7 of 10 correctly"), then a table with a caption.

---

## 9. Phase 4 — Track

- **What has been heard** (`0015`): a bitmap of heard segments per reader and book, reported by `usePlayer` together with the existing progress saves. A book of about 5,000 sentences needs about 625 bytes. A chapter counts as heard when its whole page range has been.
- **Spaced review:** Leitner boxes 1–5, reviewed after 1, 2, 4, 8 and 16 days, counted in `Asia/Colombo` time.
  - A correct answer moves a question up one box. A wrong answer sends it back to box 1.
  - It uses the quiz screen.
- **`/progress` is text first:**
  1. A summary sentence: "You have heard 3 of 9 chapters completely; 4 questions are due today."
  2. Then a table per book, with a caption and the columns Chapter · Heard · Last quiz · Best · Due.
  3. Then "Revise next", as links.
  - **No information is carried only by a chart.**
- **The teacher's view** shows only students who have chosen to share, and only class books. It never shows a student's private books, bookmarks or questions. It is a list of students, each opening their own table, because a grid of students by chapters is not navigable by ear. It shows how many students are not sharing, and offers a CSV download.
- **Consent** is an unticked checkbox with a plain-language explanation when a student joins a class. It can be changed or withdrawn from `/classes`.

## 10. Phase 5 — Reader additions

- **5a Pasted text.** This is a `CLAUDE.md` initial-release item that was never built.
  - `POST /documents/text` takes up to 200,000 characters and splits them into parts of about 3,000 characters at paragraph breaks. The interface calls them **"sections", never pages**.
  - Pasted text arrives without font information, so text in a legacy encoding is flagged `needs_review` and never converted.
- **5b In-book search.** `GET /documents/{id}/search` returns two lists: exact matches in book order, and BM25 matches over the memoised passages. Results cue without playing, and the reading position is kept. This merges quality-track item 20.
- **5c Report a problem** (`0016`). Available from any sentence, any quiz question and the accessibility statement. The report kinds are pronunciation, extraction, question, accessibility and other. A teacher sees reports on their own books.
- **5d Offline chapter download** (#32).
  - A download manifest lists a chapter's pre-rendered Opus clips.
  - A hand-written `sw.js` caches only explicit downloads.
  - The offline screen shows each download's size and a remove button, and uses the browser's storage estimate.
  - **Caches are cleared on sign-out and account deletion**, because phones are shared.

---

## 11. Phase 6 — Evaluation, and Phase 7 — Release

### 11.1 Evaluation: the dissertation's contribution

A new `evaluation/` folder holds the protocol, ethics and consent templates, the runners,
and the analysis. **Only aggregate results are committed.** `scripts/verify-repo-hygiene.sh`
is extended to enforce that.

| Research question | Design | Measures |
| --- | --- | --- |
| **RQ1 Does the verifier make generated questions safe?** | An ablation on the same held-out chapters, split by book, under three conditions: the full graph; the graph with verification bypassed (a flag that exists **only** in the evaluation runner, never as an environment variable); and the graph without the blind check. At least two Sinhala subject teachers rate the questions blind, against a rubric. | Grounded rate per condition with bootstrap confidence intervals; agreement between raters (Krippendorff's α); **the verifier's false accepts, which are the safety measure**, and its false rejects, which are the cost; the spread of rejection codes, including how often joiners cause a rejection; model calls, cost and latency per accepted question |
| **RQ2 Graph against cloze** | Teacher ratings, real review data and student attempts | How often teachers approve each, how long approval takes, how hard each question is, how well each separates stronger from weaker students, and student preference |
| **RQ3 Can blind students complete the loop alone?** | A formative study with counterbalanced tasks: find and hear a chapter; ask a question and hear the source; take a quiz and hear the source of a missed question; find what to revise. Plus a teacher publishing task. | Completion, time, assistance needed, errors, UMUX-Lite (translation not validated; we will say so), think-aloud notes, and the assistive technology and device used. **No claim about learning gains.** |
| **RQ4 Does pre-rendering fix latency and cost?** | On-demand against pre-rendered audio, on a declared cheap Android phone with network throttling | First audio at p50 and p95; CPU hours against GPU seconds; cost per audio hour; storage for WAV against Opus; a blind listening comparison of the two |
| Existing | As in `CLAUDE.md` | Retrieval Recall@5, citation support and abstention; OCR character error rate; segmentation |

**Ethics.** Institutional approval and informed consent, with **guardian consent for minors**,
come before any study involving students.

### 11.2 Release

Quality-track items 46–50: staging, observability, load and failure tests, a rehearsed
rollback, and the release candidate. Object storage (item 43) moves earlier, ahead of
production pre-render.

---

## 12. The quality track

[`upgrade-roadmap-50-commits.md`](upgrade-roadmap-50-commits.md) runs alongside these phases
as the hardening track. Each phase gate also checks the quality-track items it contains.

| Quality-track items | Where they now live |
| --- | --- |
| 2, 4 (browser tests, axe in Chromium) | Phase 0.9 |
| 6 (page titles and shell) | Phase 0.7 and Phase 1 |
| 8 (back navigation) | Phase 1 |
| 14 (detailed preparation progress) | Phase 0.6 |
| 20 (document search) | Phase 5b |
| 25 (offline download) | Phase 5d |
| 33 (extraction review) | Phase 2 (§7.3) |
| 41 (replace the identity header) | Phase 1 |
| 45 (quotas) | Phase 1 (§6.4) |
| 43 (object storage) | **Earlier**: before production pre-render |

**Corrections to the roadmap:**
- **#31 is already done.** The FM-Abhaya converter exists (`legacy_fm_abhaya.py`, with tests). Replace the item with an *evaluation* of that converter.
- **#7 should say 48 px, not 44.** The binding token is `--tap: 48px`. 44 is WCAG's floor, not our target.
- **#24 (a VITS voice) needs a product decision first.** A second voice has its own licence and its own evaluation, and `CLAUDE.md` forbids substituting voices silently.
- **#13 is partly done.** DOCX, PNG and JPEG upload already exists.
- **#42 is largely done.** Numbered migrations with an advisory lock already exist.

## 13. Migrations and configuration

| Migration | Adds |
| --- | --- |
| `0006_document_scoped_audio` | Audio primary key `(document_id, cache_key)` (landed) |
| `0007_job_leases` | Job heartbeat and lease (landed) |
| `0008_job_progress` | Pages done and total in the current stage (landed) |
| `0009_roles_recovery_audit` | User roles, recovery codes, teacher invitations, audit events (landed) |
| `0010_classes` | Classes with a join code, and members with state and progress consent (landed) |
| `0011_publishing` | Published books, pinned versions, rights attestations, page reviews (landed) |
| `0012_teacher_resets` | Thirty-minute reset codes a teacher makes for their own students, and whether the student has been told |
| `0013_quizzes` | Quizzes (questions as one JSON document per quiz) and each reader's latest answers (landed) |
| `0014_compact_audio` | Opus audio |
| `0015_tracking` | Heard segments, review cards |
| `0016_feedback` | Problem reports |

Numbers are fixed when a migration merges. Those for later phases are the order we expect,
and may shift if work lands in a different order.

All of them follow the conventions in `postgres.py`: never edit an applied migration;
ownership in the `WHERE` clause; `ON DELETE CASCADE` from `documents`; ISO text timestamps;
`ON CONFLICT` for upserts.

**New configuration.** Every item follows the adapter pattern, is reported in `/readiness`,
and is documented in `.env.example` in the same pull request that adds it.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SINHALA_READER_SECRET` | none; fatal in sessions mode | Signs CSRF tokens |
| `SINHALA_READER_COOKIE_SECURE` | `true` | `false` only for plain-HTTP development |
| `SINHALA_READER_RATE_LIMIT` | `memory` | `redis` when there is more than one process |
| `SINHALA_READER_TRUSTED_PROXY` | off | Trust `X-Forwarded-For` from a TLS front |
| `SINHALA_READER_QUIZ` | `cloze` | `graph` needs Celery and a Gemini key |
| `SINHALA_READER_QUIZ_MODEL` | the answer model | The drafting model |
| `SINHALA_READER_QUIZ_CHECK_MODEL` | the planning model | The blind check; `off` disables it |
| `SINHALA_READER_TIMEZONE` | `Asia/Colombo` | Due dates for review |
| `SINHALA_READER_TTS` | `development` | Gains `modal` |

## 14. Team tracks

These are proposals: swap them freely and say so on the epic, as #34 does.

| Track | Who | Owns |
| --- | --- | --- |
| **A: backend and data** | Heshan | 0.2–0.6; sessions, roles, rate limits and recovery; the store and the access matrix; migrations; quiz and tracking APIs |
| **B: frontend and accessibility** | Kusal | 0.7–0.9; the portal and public pages; every new screen; the NVDA and TalkBack passes at each gate; the quality track |
| **C: worker, voice and evaluation** | Lasana | 0.1; pre-render and the voice worker; the Modal adapter and Opus; both quiz generators; the `evaluation/` harness |

Tracks A and B meet at `apps/web/src/lib/types.ts`, which `npm run verify:contract` checks
against the API schema. B can build screens against Playwright mocks before A's endpoints
land.

## 15. Risks

| Risk | Mitigation |
| --- | --- |
| **Minors' personal data** (Sri Lanka's PDPA, No. 9 of 2022) | Legal review and guardian consent before any pilot. Progress sharing is off by default. Collect only what is needed. We do not claim compliance. |
| **Textbook rights** | An attestation is not clearance. Sharing stays class-only, audited and withdrawable. Public sharing stays out of scope. |
| **The XTTS licence (CPML) is non-commercial**, and that applies to distributed pre-rendered audio too | Keep the project academic and non-commercial, and say so on `/terms`. Resolve the licence before any commercial use. |
| **No GPU** while the upload to Modal is blocked by the network | Pre-render is chunked and resumable, current chapter first. The Modal adapter sits behind configuration. Progress is reported honestly. |
| **The verifier rejects too much** (joiners, inflection) | Measure it in RQ1 and relax a check only with evidence. Cloze is always available. |
| **Gemini models are retired or change** | Versions are pinned and configurable. A failed quiz says so, and offers cloze as a choice. |
| **LangGraph's dependencies grow or churn** | Worker-only image target, constraints file, and the import-isolation test. |
| **Teacher resets are abused** | Only for the teacher's own active students; single use, 30 minutes, audited; the student is told. |
| **The page title is announced twice** (Next's route announcer plus our heading focus) | Checked with NVDA in 0.7 before it spreads. |
| **The pass-through mishandles uploads, ranges or long answers** | Streaming handler, `/api` excluded from `proxy.ts`, a 120 s timeout, and Range tests in Playwright. |
| **Accessibility regresses on complex new screens** | Axe, contrast and reflow checks on every new screen, and NVDA and TalkBack at every gate. |
| **The Sinhala interface doubles in size before review** | Review in step with each phase; `content.ts` reviewed on its own. |

## 16. Decisions and the alternatives we rejected

Recorded so that none of these is reopened by accident. Reopening one is fine; it needs a
pull request that updates this section.

| Decision | Rejected alternative | Why |
| --- | --- | --- |
| The portal lives inside the same app | A separate marketing site | One deploy, one design system, one accessibility suite |
| Public pages in Sinhala only | Sinhala and English | Less to write and review; the product is Sinhala-first |
| An httpOnly cookie through a same-origin route handler | A bearer token in localStorage | pdf.js renders untrusted PDFs in our page; a cookie cannot be stolen by script; CORS disappears |
| A route handler for the pass-through | Next `rewrites()` | Rewrites are fixed at build time, time out at 30 s, and sit behind a 10 MB body buffer |
| Teachers created by an admin or an invitation | Choosing a role at registration | Anyone could claim to be a teacher |
| Recovery codes and teacher-issued resets | Email reset | We have no email infrastructure, and many students have no reliable address |
| Class sharing only | Sharing between any readers; a shared audio cache across private uploads | Rights, and a shared cache would reveal who holds which file |
| LangGraph for the quiz loop only | LangChain across the study stack | Answering is a single pass and already works; a framework layer would sit exactly where the read-mode guarantees live |
| Our own calls through `gemini._post` | LangChain model wrappers | LangGraph orchestrates; we keep the transport we have tested |
| Teacher review as a database status | LangGraph interrupts and checkpointing | Checkpointer tables fall outside our migrations and deletion; a pause would span deployments; approval must be a queryable fact |
| A deterministic verifier as the judge | A model judging correctness | A model's opinion can reject a question but never establish that it is correct |
| Cloze as the default generator | The graph as the default | No provider needed; verifiable by construction; the product must ship without Gemini |
| torch 2.8.0 in every runtime | Installing torchcodec and FFmpeg | Smaller, and consistent with the manifest's recorded decision |
| No time limits on quizzes | Timed quizzes | WCAG 2.2.1; a screen-reader user needs longer, and should |
