# Interface audit — September 2026

A click-through of every screen and control, as a student and as a teacher, with
the mouse and with the keyboard alone, at 1280 px, at 360 px phone width, and at
300% zoom (a 427 × 300 CSS-pixel viewport). This file is the findings list; the
**Status** column says what happened to each one.

## How it was run

- The stack from `infra/docker-compose.yml`, with the web app from the working
  tree (`npm run dev` on port 3200) against the running API.
- **The placeholder voice, not the real one.** With `compose.voice.yml` the API
  loads the 5.6 GB checkpoint, reaches about 8 GB, and is killed for memory by a
  10.7 GB WSL machine, about once a minute (eight restarts in 43 minutes). The API
  container was recreated without the overlay for the audit, so every "play"
  below is the labelled tone (E1).
- Test books made for the purpose, not real ones: a three-page Sinhala history
  PDF printed from HTML by Chrome, a Word document, a PNG of the same page, a
  corrupt `.pdf`, and pasted text.
- Accounts: a student, a teacher (granted with `sinhala_reader.admin grant-role`),
  and a throwaway account that was deleted at the end.
- Tools: the in-app browser, a probe script (titles, headings, target sizes,
  unnamed controls, sideways overflow, overlapping controls), and the existing
  checks. **No screen reader was used.** Everything below about what NVDA or
  TalkBack would say is inferred from the accessibility tree, not heard.

Severity: **Critical** — a core task cannot be done by someone using assistive
technology or zoom. **High** — it can be done, but badly enough to stop most
people. **Medium** — a real barrier or inconsistency with a workaround.
**Low** — polish.

## Environment

| ID | Finding | Severity | Status |
| --- | --- | --- | --- |
| E1 | The API is killed for memory while loading the real voice, and restarts about once a minute. Every request in flight fails with "unexpected error", including registration. | High | Not fixed here: needs more memory for WSL, or loading the checkpoint with less headroom (Phase 7 profiles the worker). Worked around for the audit. |
| E2 | `browser-tests` pins Playwright 1.55.1, whose Chromium build (1193) was not installed on this machine. | Low | Ran against the installed build through a scratch config; nothing committed. |
| E3 | The Next dev server served 404 for every route under `/library/[id]/…` until its `.next/dev` cache was cleared. The production image was fine. | Low | Environment only. |
| E4 | `grant-role --reason local-testing` is rejected; the reasons are `verified-teacher`, `school-staff`, `correction`, `revoked`. | Low | Documented here. |
| E5 | `/readiness` says `"ocr": "broken"` from the API process while OCR works in the worker (the PNG was recognised). | Low | Not fixed: it describes the API process; worth a sentence in the runbook. |

## Findings

| ID | Screen | Steps | What happened | What should happen | Severity | Status |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | Reader | Press **කියවීම විශාල කරන්න** (expand reading) | The workspace goes blank. The hidden panel is `display: none`, so the reading panel falls into a 0-width grid track. The book cannot be read until the button is pressed again. | The reading panel fills the width. | Critical | |
| F02 | Reader, 300% zoom | Open a book at 427 × 300 | Header, toolbar, tabs and player fill the viewport; the reading panel is 0 px tall. | The page scrolls and the text is reachable. | Critical | |
| F03 | Every signed-in page, 360 px and 300% zoom | Open any page | The page scrolls sideways: 144 px in the reader at 360 px, 76 px on every page at 300%. The five nav links cannot wrap, and the shell's one grid column is as wide as its widest child. | No horizontal scroll at 320 px. | High | |
| F04 | Every page, phone and zoom | Scroll | The sticky masthead is 219 px of a 780 px phone screen (28%) and 148 of 354 px at 300% zoom. | It scrolls away when there is no room for it. | High | |
| F05 | Many | Keyboard only | **Focus falls to `<body>`**, so a keyboard or screen-reader user is thrown back to the top of the page, after: (a) saving or cancelling a rename — the dialog focuses the book's button while it is still modal and everything else is inert; (b) deleting a book; (c) **සෙවීම හිස් කරන්න** (clear search); (d) **නවත්වන්න** (stop) — the button disables itself; (e) adding a bookmark — the button disables itself while saving; (f) asking a question — the field and button disable themselves; (g) **පරීක්ෂා කරන්න** (check answer) — the button is replaced; (h) leaving an offline chapter; (i) removing an offline chapter; (j) removing a bookmark; (k) unpublishing a book; (l) removing a student; (m) deleting a class. | Focus moves to the next sensible control or heading. | High | |
| F06 | Reader, pasted text | Paste text and open it | The English note *"Pasted text. It is divided into sections…"* is shown twice, under "about this book" and "about this page"; the left panel says the Word file's text is on the right and offers to download "the original file"; the page tools (sync, expand original) apply to a page that does not exist. | One reading panel, no original-page panel, the note once. | High | |
| F07 | Reader, share page | Open a book with notes | Every note written by the pipeline (`file_extract.py`, `pdf_extract.py`, `ocr.py`) is English prose inside a Sinhala page, and is read by the Sinhala voice because nothing marks it `lang="en"`. | Notes in Sinhala, from stable codes the interface translates. | High | |
| F08 | Extraction | Upload a Sinhala PDF printed by Chrome | The text comes out garbled — repeated clusters (`ශ්‍රීශ්‍රීශ්‍රී`) and NUL characters — and every page is **accepted**. The garbage is narrated, searched, quoted in answers, and made into quiz questions. | Pages like this are flagged for review or recognised by OCR. | High | |
| F09 | Everywhere | Measure targets | The 48 px rule (`--tap`) is broken by `.btn-sm` (36 px), used for about twenty reader controls, every book card action, the header's sign-in links, dialog close buttons and the offline player; nav links (42 px), the account link (28 px), segmented options (40 px), the speed select (42 px) and the class-progress `<summary>` (29 px). | At least 48 px. | High | |
| F10 | Sign in, register, recover, paste, classes | Look at the fields | Email fields and every input with no `type` attribute (recovery code, name, class code, class name, pasted-text title) are unstyled: grey browser boxes, 35 px tall. | The same field style as the password fields. | Medium | |
| F11 | Reader, desktop | Look at the foot of the reading panel | The **පොත ගැන අසන්න** (ask) button covers **ගැටලුවක් වාර්තා කරන්න** (report a problem) and **සුරැකි පරිච්ඡේද** (saved chapters). | Nothing covers a control, including a focused one (WCAG 2.4.11). | Medium | |
| F12 | Ask drawer | Open it before asking | It says the answers are the book's own words. This server writes answers with Gemini; the label only corrects itself after the first answer. | The right claim from the start: `/readiness` reports the answer mode. | Medium | |
| F13 | Ask drawer | Press a citation on another page | The page opens, but the cited sentence is not cued; the reader has to find it. | The cited sentence is cued, not played. | Medium | |
| F14 | Search, practice, report | Read the back link | **පොත් ලැයිස්තුවට** ("to the book list") goes to the book. | Say where it goes. | Medium | |
| F15 | Reader, phone | Arrow keys on the tabs | `role="tab"` without the arrow keys the pattern promises. | Left/Right, Home/End move between tabs. | Medium | |
| F16 | Reader | Add a bookmark, then try to undo | **ආපසු හරවන්න** (undo) is earlier in the tab order than the bookmark button, and disappears after 8 seconds even while focused. | Reachable next, and not removed while in use. | Medium | |
| F17 | Front door | Read the four steps | Practise and Progress are marked **තවම නැත** ("not yet"), and classes "still being prepared"; all three have shipped. | Current. | Medium | |
| F18 | `/join/<code>` | Follow a class link | 404. The route is in the product plan (§6.1); joining works only by typing the code on `/classes`. | The link opens the join form with the code filled in. | Medium | |
| F19 | Any unknown address | Mistype a URL | Next's default 404, in English, unbranded, with no way back. | A Sinhala page with a way home. | Medium | |
| F20 | Practice | Answer, press **මූලාශ්‍රය අසන්න** (hear the source), come back | The reader has no way back to the quiz; Back lands on the quiz list, and starting again begins at question 1. Plan §8.7 asks for "Back to the quiz" and a resumable attempt. | Back to the same question. | Medium | |
| F21 | Offline, bookmarks | List the buttons | **අසන්න — මුළු පොත** and **ඉවත් කරන්න — මුළු පොත** ("whole book") with no book name, so two saved books give identical buttons; bookmarks are grouped under the file name even after a rename. | Every repeated control names its book. | Medium | |
| F22 | Library | Type in the search box | Nothing tells a screen-reader user how many books match. | The count, politely. | Medium | |
| F23 | Library, empty | Look for pasted text | Only **පොතක් එක් කරන්න** (add a book); the paste link appears after the first book exists. | Both ways in, from the start. | Medium | |
| F24 | Accessibility statement | Read the report links | The first goes to GitHub Issues — an English site that needs an account — without saying so. | Say so, or lead with the in-app form. | Medium | Needs a decision |
| F25 | Share a book | Review a flagged page | No way to see the page being judged; each arrow key in the radio group saves a decision, and nothing is announced. | A link to the page; a confirmation. | Medium | |
| F26 | Class page | **සිසුවා ඉවත් කරන්න** (remove student) | Removed at once, no confirmation. | A confirmation, like deleting a class. | Medium | Needs a decision |
| F27 | Library | Sign out | The tab still says **මගේ පොත්** (my books) over the sign-in panel. | The panel's own title. | Low | |
| F28 | Every page | Use the skip link | `<main id="main">` is not focusable, so focus does not reliably move into it. | `tabindex="-1"` on the target. | Low | |
| F29 | Every page | Choose a theme, reload | The system theme paints first; the saved one arrives after hydration. | No flash (Phase 5's cookie). | Low | Phase 5 |
| F30 | Library, teacher reset notice | Read the date | "September 27, 2026 at 8:16 PM" inside a Sinhala sentence. The code asks for `si-LK`; this browser has no Sinhala locale data and falls back. | A Sinhala date on every browser. | Low | |
| F31 | Class page | Read the tab title | **පන්ති** (classes), not the class's name. | The class's name. | Low | |
| F32 | Class page | **නව කේතයක් සාදන්න** (new code) | The old code stops working at once, with no warning. | Say so first. | Low | |
| F33 | Report form | Send a report | The form never says which book or sentence it is about; the thank-you is both focused and announced, so it is read twice. | Name the subject; say it once. | Low | |
| F34 | Practice | Finish a quiz | A score heading only; plan §8.7 also asks for a results table and **Hear the question**. | As planned. | Low | |
| F35 | Account | List the form fields | Three **වත්මන් මුරපදය** and four **මුරපදය පෙන්වන්න** with identical names; a wrong password is not tied to its field (`aria-invalid`, `aria-describedby`). | Distinct names; the error on the field. | Low | |
| F36 | Teacher's reports | Read a report | No way to mark it handled; the back link reads **පන්තියක් සමඟ බෙදා ගන්න** (share with a class). | A back link that says "back". | Low | |
| F37 | Library | Upload `පිටුව.png` | The book is called "පිටුව.png", extension included. | The name without the extension. | Low | |
| F38 | Library | Heading order | "Continue reading" (`h2`) comes before the page's `h1`. | `h1` first. | Low | |
| F39 | Library | Class books | A class book opens from its 30 px title; your own books have a **කියවීම අරඹන්න** button. | The same control for both. | Low | |
| F40 | Classes, as a teacher | Open `/classes` | "Join a class" comes first and "classes you teach" last. | A teacher's own classes first. | Low | |
| F41 | Reader | Press next sentence while paused | Playback resumes. A press, so within the rules, but worth a decision. | — | Low | Needs a decision |

## Not tested, and why

- **Pre-render** (**දැන් හඬට හරවන්න**): the worker still had the real voice, and
  starting it would have loaded the checkpoint into the worker as well, with the
  same memory failure as E1.
- **Retry a failed book**: a corrupt file fails permanently (`can_retry` is
  false, correctly), and a transient failure could not be produced on demand.
  The unit tests cover the button.
- **Revise links** (`?review=`): nothing is due until the day after an answer.
  The unit tests cover them.
- **Model-drafted quizzes**: `SINHALA_READER_QUIZ` is `cloze` here.
- **Real narration, speed and pitch**: the placeholder tone only.
- **A screen reader**: none. The NVDA and TalkBack passes each phase gate asks
  for are still owed.
