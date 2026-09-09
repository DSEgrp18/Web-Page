# apps/web

The reader: add a Sinhala book, choose a page, listen, pause, and come back to
where you were — in a browser, in Sinhala, by keyboard, and with a screen reader.

This is the other half of CLAUDE.md's step 3. The API had the spine; this is the
part a person actually touches.

## The accessibility decisions, and why

These are the choices that would be invisible in a screenshot and decisive in
NVDA. They are the substance of this directory, not decoration on it.

**Each sentence is a button whose accessible name is the sentence.** Navigating
by button is the fastest way through a page in NVDA and TalkBack, so one stop
both reads the sentence and offers to play it. The obvious alternative — a small
play icon beside each sentence — produces a list of forty buttons all called
"අසන්න", which is a list of nothing.

**Nothing plays on load. Ever.** Not on arrival, not on a page change, not on
resume. Resume restores the position and waits for a press. A page that starts
talking talks over the screen reader announcing it.

**Continuous narration is not announced.** When one sentence ends and the next
begins, nothing goes to a live region. The reader is listening to the book; a
screen reader naming every sentence boundary competes with the thing they asked
for. Position is announced when they *ask*, by pressing a control.

**Polite for progress, assertive for errors, and nothing else.** A live region
that interrupts constantly is one a reader turns off. Announcements are also
cleared after four seconds, because a message left in a live region is read
again by anyone browsing the page afterwards.

**Focus moves on navigation, not on arrival.** Pressing "next page" moves focus
to the page heading, so the change is noticed. Arriving at the page does not,
because that would yank a screen reader out of what it is already reading.

**There are no single-key shortcuts.** `p`, `n` and `space` collide with NVDA's
browse-mode quick navigation, where single letters jump between elements. Every
control is a real button. Shortcuts can come later, scoped to the player and
tested with a real screen reader rather than guessed at.

**`lang="si"` on the document.** This is what makes NVDA and TalkBack read the
interface with a Sinhala voice. Without it the controls are read by an English
synthesiser and are unintelligible even when the words are right.

## What is not verified

**No testing with assistive technology has been done.** None. CLAUDE.md treats
inability to upload, play, pause, navigate or resume with assistive technology
as a release blocker, and nothing here has been in front of NVDA, TalkBack, or a
person who uses either.

`tests/a11y.test.tsx` runs axe over the core flows and passes. Automated rules
catch a fraction of real barriers, and none of the decisions listed above:
whether the announcements land at a useful moment, whether the sentence list is
navigable at speed, whether any of it makes sense.

**The Sinhala has not been reviewed by a native speaker.** Every string is in
`src/lib/strings.ts`, in one file, so that review is a single read. Until it
happens, a screen-reader user hears text that has been checked by nobody.

**Colour contrast** was calculated by hand — the ratios are recorded in
`globals.css` — not measured in a browser, because axe cannot compute contrast
in jsdom.

## Run it

The API must be running, and must be told this origin is allowed:

```bash
# terminal 1 — the API
cd services/api
SINHALA_READER_AUTH=development \
SINHALA_READER_ORIGINS=http://localhost:3000 \
PYTHONPATH="src:../worker/src:../tts/src" \
  python -m uvicorn sinhala_reader.app:app --reload

# terminal 2 — the reader
cd apps/web
npm install
npm run dev
```

Then `http://localhost:3000`. It asks for a name; that name is the identity sent
in `X-Reader-User`, and the interface says plainly that it is not a login.

Point it somewhere else with `NEXT_PUBLIC_READER_API`. That is an address, not a
secret — no secret ever enters a browser bundle.

## Checks

```bash
npm run lint         # eslint, including jsx-a11y
npm run typecheck    # tsc --noEmit
npm test             # vitest, including the axe smoke test
npm run build        # the production build
```

`npm run verify:contract` compares `src/lib/types.ts` against the API's own
OpenAPI schema. The types are hand-written; this is what stops them drifting
silently, which fails in the worst way available — the API renames `page_label`,
the interface reads `undefined`, and the reader is told the printed page number
is missing on every page of the book. CI runs it in the **Reader API** job,
where FastAPI is already installed, without starting a server:

```bash
PYTHONPATH="services/api/src:services/worker/src:services/tts/src" \
  python -c "import json, sinhala_reader; print(json.dumps(sinhala_reader.create_app().openapi()))" \
  > /tmp/openapi.json
node apps/web/scripts/verify-contract.mjs /tmp/openapi.json
```

## How it is put together

| | |
| --- | --- |
| `src/lib/types.ts` | The API contract, mirroring `schemas.py`. |
| `src/lib/client.ts` | Every request. Turns HTTP status into a small set of named failures. |
| `src/lib/usePlayer.ts` | One audio element, a queue of sentences, instant pause. |
| `src/lib/strings.ts` | Every word the interface says. **Awaiting native-speaker review.** |
| `src/lib/identity.ts` | The development stand-in for accounts. |
| `src/components/Announcer.tsx` | The two live regions, and the rules for using them. |
| `src/components/Library.tsx` | Upload, list, delete. |
| `src/components/Reader.tsx` | The reading screen. |

Audio is fetched as a blob rather than pointed at with `<audio src>`, because
that attribute can carry neither the identity header nor a reading of
`X-Reader-Real-Model`. Clips are kept in memory (eight of them) so that pressing
a sentence twice does not ask a GPU to make it twice.

## Not implemented

Bookmarks, chapter downloads, offline listening, questions and answers, and
sentence highlighting against the page image. Playback speed is exposed but its
intelligibility at 1.5× and 2× is untested against the real model, which does
not exist here yet: **the audio is a placeholder tone**, and the interface says
so on the page and out loud the first time one plays.
