# Building the reader interface

**Read this before your first UI issue.** It is the whole of the UI/UX knowledge
this project needs. You do not need design experience to follow it — every rule
here is testable, and every one says why it exists.

If a rule and a visual design disagree, **the rule wins**, and open an issue
about the design. A mockup shows what a page looks like to someone who can see
it. Most of our readers cannot.

---

## 1. Who you are building for

Picture three people. Every decision below serves at least one of them.

**Nimali** is blind and uses **NVDA** on Windows with a Sinhala voice. She never
sees the screen. She moves through a page by pressing <kbd>Tab</kbd>, or by
jumping between headings, links and buttons. She hears the page one element at a
time, in order. She is a Grade 11 student and the book is her homework.

**Sahan** has low vision. He uses the same browser as you, at **300% zoom**,
with the largest text his phone allows. He sees the screen, but only a small
part of it at a time, and he cannot tell dark blue from black.

**Tharindu** uses **TalkBack** on a cheap Android phone with a small screen and
patchy data. He explores by swiping right to move to the next element, and
double-tapping to activate it.

Three things follow from this and are worth holding onto:

- **The screen reader is already talking.** Anything the page says has to fit
  around that, not shout over it.
- **Order is everything.** If it is not in the reading order, it does not exist.
- **The page is heard, not scanned.** Nimali cannot glance at a layout to work
  out where she is. Headings and names have to tell her.

---

## 2. The five rules that override everything

If you remember nothing else, remember these. Each one has already been decided,
is already implemented, and must not be undone.

### Rule 1 — Nothing plays or moves without a person asking

No autoplay on page load, on page change, or on resume. Resume restores the
position and **waits for a press**.

*Why:* a page that starts talking talks over the screen reader announcing the
page. Nimali then hears two voices at once and can work out neither.

### Rule 2 — Every control is a real `<button>` or `<a>`

Never a `<div>` with an `onClick`. Never a `<span>` with `role="button"` bolted
on afterwards.

*Why:* a real button is reachable by <kbd>Tab</kbd>, activated by
<kbd>Enter</kbd> and <kbd>Space</kbd>, announced as "button", and included when
Nimali asks NVDA to list every button on the page. A `div` is none of those, and
adding `role` and `tabindex` to fake it means reimplementing all of them by hand
and getting one wrong.

### Rule 3 — Polite for progress, assertive for errors, and nothing else

Use `say()` for progress and confirmation. Use `alert()` only for errors.

*Why:* an assertive live region **interrupts**. A page that interrupts
constantly is one Nimali turns off, and then she hears nothing at all —
including the errors that mattered.

### Rule 4 — Focus moves on navigation, never on arrival

When the reader presses "next page", move focus to the page heading. When a page
simply loads, leave focus alone.

*Why:* moving focus tells Nimali something changed. Moving it when she did not
ask yanks her out of whatever she was reading.

### Rule 5 — State is never colour alone

A highlighted sentence also carries `aria-current="true"`. A disabled button is
actually `disabled`. An error also says the word.

*Why:* Nimali has no colour. Sahan cannot distinguish some of them.

---

## 3. How to build a control

```tsx
// Good
<button type="button" onClick={play}>
  {strings.play}
</button>
```

Four things to get right, every time:

**Give it an accessible name that says what it does.** The name is the visible
text. `strings.play` is `අසන්න` — "listen". Not "click here", not an icon alone.

**If several controls share a name, distinguish them in the name itself.** A
list of ten books each with a "විවෘත කරන්න" button is a list of ten identical
buttons when Nimali lists them. Add the book's name, visually hidden if it would
clutter the layout:

```tsx
<Link href={...}>
  {strings.open}
  <span className="visually-hidden"> — {book.filename}</span>
</Link>
```

**Never replace visible text with `aria-label`.** If a button shows `අසන්න` and
carries `aria-label="Play"`, then Sahan reads one word and Nimali hears another,
and a voice-control user who says what they see is not understood. Use
`aria-label` only where there is no visible text at all, and prefer adding
visible text instead.

**Never remove the focus outline.** `outline: none` without a replacement is the
single most common way to make a page unusable by keyboard. `globals.css`
already defines a visible `:focus-visible` style; leave it alone.

---

## 4. Saying things out loud

Two live regions exist, in `src/components/Announcer.tsx`. Use them through the
hook; never add a third.

```tsx
const { say, alert } = useAnnouncer();

say(strings.prepared);        // polite — waits its turn
alert(messageFor(error.kind)); // assertive — interrupts
```

### Announce state changes, not progress ticks

```tsx
// Wrong: the library polls every 1.5 seconds
say("still preparing…");   // said 40 times, over and over

// Right: only when it actually becomes ready
if (wasPending && nowReady) say(strings.prepared);
```

### Do not narrate continuous playback

When one sentence ends and the next begins, **say nothing**. The reader is
listening to the book; a screen reader naming every sentence boundary competes
with the exact thing they asked for. Announce position only when the reader
*asks*, by pressing a control.

### Errors go to both places

`alert()` speaks it once; an `<ErrorNotice>` keeps it on screen so the recovery
button is a real control rather than a sentence that has already gone past. The
notice is deliberately **not** a live region — that would say everything twice.

---

## 5. Focus, and moving it

Move focus in exactly two situations:

1. **After navigation the reader initiated** — a new page, a new screen. Move it
   to the heading of what just appeared, which needs `tabIndex={-1}` to be
   focusable:

   ```tsx
   <h2 ref={headingRef} tabIndex={-1}>…</h2>
   // after the new page loads, and only if the reader navigated:
   if (navigatedRef.current) headingRef.current?.focus();
   ```

2. **When something the reader opened appears** — a dialog, an expanded panel.
   Focus goes into it, and returns to the control that opened it when it closes.

Never move focus on a timer, on a poll completing, or on first load.

---

## 6. Sinhala, specifically

**`lang="si"` on `<html>`** is what makes NVDA and TalkBack use a Sinhala voice.
Without it the interface is read by an English synthesiser and is unintelligible
even when the words are right. It is set in `layout.tsx`; a test asserts it.

**Every user-facing string lives in `src/lib/strings.ts`.** One file, so a native
speaker can review the whole interface in a single read. Never inline a Sinhala
string in a component, and never inline an English one either.

**Sinhala needs vertical room.** Vowel signs stack above and below the base
letter, so a Latin-default `line-height: 1.4` clips them into each other. The
body line-height is `1.8` and headings `1.5`. Do not reduce them.

**Use the font stack that is already there.** `"Noto Sans Sinhala"` first. A
fallback face loses the distinctions between similar letters, which hurts Sahan
most.

**Numbers are Western digits** (`42`, not `෪෨`), which is what Sinhala school
books print. The *spoken* form is a separate field — `spoken_text` — produced by
the server. Never show `spoken_text`; never speak `display_text` directly.

---

## 7. Colour, size and zoom

The palette is defined once, as tokens, at the top of `globals.css`. **Use the
tokens; never write a hex value in a component.** Both light and dark themes are
defined, and a colour written directly into a component will be wrong in one of
them.

| Rule | Number | Why |
| --- | --- | --- |
| Body text contrast | at least **4.5:1** | WCAG 2.2 AA |
| Large text and UI borders | at least **3:1** | WCAG 2.2 AA |
| Touch target | at least **44 × 44 px** | WCAG 2.2 Target Size; Tharindu's thumb |
| Page must work zoomed to | **400%** | WCAG 2.2 Reflow |
| Horizontal scrolling | **never**, for the page body | Sahan cannot find content off-screen |

Wide things — tables, code, diagrams — scroll **inside their own container**
with `overflow-x: auto`. The page itself never scrolls sideways.

Never disable zoom. `maximum-scale=5` is set deliberately in `layout.tsx`;
setting it to `1` is a common copy-paste that breaks the app for Sahan
completely.

---

## 8. Things that look helpful and are not

| Do not | Because |
| --- | --- |
| `role="application"` | It switches NVDA out of browse mode, and Nimali loses arrow-key reading of the whole page |
| Single-key shortcuts (`p`, `n`, <kbd>Space</kbd>) bound to the document | They collide with NVDA browse-mode quick navigation, where single letters jump between elements. Scope any shortcut to the player, and test it with a real screen reader |
| `tabindex` greater than `0` | It invents a second, competing tab order that nobody can predict |
| A spinner with no text | It says nothing to Nimali. Announce with `say()`, and give it a visible label |
| `aria-live` on something that already moves focus | Both fire, and the message is read twice |
| Placeholder text instead of a `<label>` | The placeholder disappears on typing, and some screen readers never announce it |
| `title` attributes as the only description | Not announced reliably, not reachable by keyboard, not visible on touch |
| Hiding a section with `display: none` when it should be reachable | Also hides it from screen readers; use it deliberately, not accidentally |

---

## 9. Before you open a pull request

Run these five. They take about ten minutes together and catch most of what
matters.

1. **`npm run lint`** — includes `eslint-plugin-jsx-a11y`.
2. **`npm test`** — includes the axe smoke test over the core flows.
3. **Unplug your mouse.** Do the whole flow with <kbd>Tab</kbd>,
   <kbd>Shift+Tab</kbd>, <kbd>Enter</kbd> and <kbd>Space</kbd>. If you cannot
   reach a control, or cannot see where focus is, it is broken.
4. **Zoom to 400%** (<kbd>Ctrl</kbd> and <kbd>+</kbd>). Nothing may be clipped
   and the page must not scroll sideways.
5. **Turn on NVDA and listen to your change.** Even five minutes finds things no
   automated tool does. <kbd>Ctrl</kbd> silences it; <kbd>Insert</kbd> +
   <kbd>Q</kbd> quits.

**Automated checks are not evidence of accessibility.** axe catches perhaps a
third of real barriers and none of the judgement calls — whether an announcement
lands at a useful moment, whether a list is navigable at speed, whether the
Sinhala makes sense. Passing CI means you have not obviously broken anything. It
does not mean it works.

---

## 10. Where things live

| Path | What it is |
| --- | --- |
| `apps/web/src/lib/strings.ts` | Every word the interface says. Sinhala only. |
| `apps/web/src/lib/client.ts` | Every request to the API. Turns HTTP status into named failure kinds. |
| `apps/web/src/lib/types.ts` | The API contract. Hand-written; `npm run verify:contract` checks it. |
| `apps/web/src/lib/usePlayer.ts` | Playback: one audio element, a queue of sentences, instant pause. |
| `apps/web/src/components/Announcer.tsx` | The two live regions and the rules for using them. |
| `apps/web/src/components/AppFrame.tsx` | Skip link, masthead, `<main>`, the identity step. |
| `apps/web/src/components/Library.tsx` | Upload, list, delete. |
| `apps/web/src/components/Reader.tsx` | The reading screen and the player controls. |
| `apps/web/src/app/globals.css` | Colour tokens, type, focus, touch targets. |
| `apps/web/tests/a11y.test.tsx` | The axe smoke test. Add your new screen to it. |

Run it with `npm run dev` in `apps/web`, against the API started as described in
[`services/api/README.md`](../services/api/README.md). The API must be told your
origin is allowed, or the browser blocks every request before it is sent.

---

## 11. When you are unsure

Ask in the issue rather than guessing. Two questions answer most of it:

> **Could Nimali do this with her eyes closed and no mouse?**
>
> **Does the page say what happened, once, at the moment it happened?**

If the answer to either is no, the change is not finished — however good it
looks.
