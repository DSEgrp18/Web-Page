"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { usePreferences } from "@/components/PreferencesProvider";
import { useReader } from "@/components/ReaderProvider";
import { PANEL_MIN_REM } from "@/components/SplitView";
import { ApiError } from "@/lib/client";
import { ASSISTANT_MAX_REM, ASSISTANT_MIN_REM, DEFAULTS } from "@/lib/preferences";
import { messageFor } from "@/lib/strings";
import type { Exchange, StudyAnswer } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Quoted, Typed } from "@/components/BookText";

/** How many earlier exchanges a question carries. The API accepts at most 6. */
const HISTORY_LIMIT = 4;

/** Arrow keys move the Ask panel's edge this many rem; Page Up/Down, more. */
const WIDTH_STEP = 2;
const WIDTH_BIG_STEP = 6;

function rootPx(): number {
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * The widest the Ask panel may be in this window: the book beside it keeps
 * room for one panel at its minimum, and a little for the divider.
 */
function widestRem(): number {
  const windowRem = Math.floor(window.innerWidth / rootPx());
  return Math.max(ASSISTANT_MIN_REM, Math.min(ASSISTANT_MAX_REM, windowRem - PANEL_MIN_REM - 2));
}

/**
 * The Ask panel's edge, on a wide screen: a window splitter like the book's
 * own divider. The panel sits beside the book, not over it, so moving this
 * edge moves the book's right-hand edge with it. The width is kept in the
 * reader's preferences and said as a share of the screen.
 *
 * Left widens the panel (the edge moves left), Right narrows it; Page Up and
 * Page Down do the same in bigger steps; Home is the narrowest, End the
 * widest, Enter the usual width.
 */
function AssistantEdge({ panel }: { panel: React.RefObject<HTMLElement | null> }) {
  const strings = useStrings();
  const { preferences, set } = usePreferences();
  const width = preferences.assistantWidth;
  const dragging = useRef(false);

  const setWidth = useCallback(
    (rem: number) =>
      set("assistantWidth", Math.max(ASSISTANT_MIN_REM, Math.min(widestRem(), Math.round(rem)))),
    [set],
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = {
      ArrowLeft: WIDTH_STEP,
      ArrowRight: -WIDTH_STEP,
      PageUp: WIDTH_BIG_STEP,
      PageDown: -WIDTH_BIG_STEP,
    };
    if (event.key in moves) {
      event.preventDefault();
      setWidth(width + moves[event.key]!);
    } else if (event.key === "Home") {
      event.preventDefault();
      setWidth(ASSISTANT_MIN_REM);
    } else if (event.key === "End") {
      event.preventDefault();
      setWidth(widestRem());
    } else if (event.key === "Enter") {
      event.preventDefault();
      setWidth(DEFAULTS.assistantWidth);
    }
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current) return;
      const right = panel.current?.getBoundingClientRect().right;
      if (right === undefined) return;
      setWidth((right - event.clientX) / rootPx());
    };
    const stop = () => {
      dragging.current = false;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [panel, setWidth]);

  const percent =
    typeof window === "undefined"
      ? null
      : Math.round(((width * rootPx()) / Math.max(1, window.innerWidth)) * 100);

  return (
    // A focusable window splitter; see SplitView for why the interaction
    // rule is disabled here.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div
      className="assistant-edge"
      role="separator"
      tabIndex={0}
      aria-orientation="vertical"
      aria-label={strings.assistantResize}
      aria-valuenow={width}
      aria-valuemin={ASSISTANT_MIN_REM}
      aria-valuemax={ASSISTANT_MAX_REM}
      aria-valuetext={percent === null ? undefined : strings.assistantWidthValue(percent)}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        dragging.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onDoubleClick={() => setWidth(DEFAULTS.assistantWidth)}
    >
      <span className="split-grip" aria-hidden="true" />
    </div>
  );
}

/** One exchange. Kept in memory only: a question is about a book, not a record. */
interface Turn {
  id: string;
  question: string;
  answer: StudyAnswer | null;
  error: string | null;
}

/**
 * Asking about the book, beside the book.
 *
 * ## What this actually is, and what it is not
 *
 * The API's answerer is **extractive**: it retrieves passages from this
 * document and returns the book's own sentences with the page they came from.
 * It does not summarise, explain, or generate prose, and nothing here pretends
 * otherwise — the answers are labelled as the book's words, and there are no
 * "summarise this page" or "explain this section" suggestions, because those
 * would be buttons for a capability that does not exist. CLAUDE.md is explicit
 * that a model must never supply the words a reader hears as the document, and
 * the honest interface for an extractive answerer is one that says so.
 *
 * When a generative answerer arrives, this is where it goes, and the label
 * changes with it.
 *
 * ## A drawer, not a dialog
 *
 * It does not trap focus or make the book inert, because the book is the thing
 * being asked about and a reader may well want to move through it with the
 * drawer open. `aria-expanded` and `aria-controls` say what the button does;
 * Escape closes; focus goes to the question field on open and back to the
 * button on close.
 *
 * ## The conversation survives being minimised
 *
 * Closing hides the drawer; it does not clear it. Somebody who closed the panel
 * to read a paragraph and reopened it should find their place, not a blank
 * form. Clearing is a separate, deliberate action.
 *
 * ## Answers arrive politely
 *
 * `aria-live="polite"`: an answer that interrupts narration mid-sentence is
 * worse than one that waits for a gap, and CLAUDE.md reserves assertive for
 * urgent errors. A study answer is never urgent.
 */
export function AssistantDrawer({
  documentId,
  bookTitle,
  pageIndex,
  selection,
  onClearSelection,
  onOpenCitation,
  onGoToPage,
}: {
  documentId: string;
  bookTitle: string;
  pageIndex: number;
  /** Text the reader highlighted, attached to the next question. */
  selection: string;
  onClearSelection: () => void;
  /** Move the reader to a cited sentence. False when it is not on this page. */
  onOpenCitation: (segmentId: string) => boolean;
  /** Turn to a page, and cue a sentence on it once it has loaded. */
  onGoToPage: (index: number, segmentId?: string) => void;
}) {
  const strings = useStrings();
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const { preferences } = usePreferences();
  const panel = useRef<HTMLElement>(null);

  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [asking, setAsking] = useState(false);

  /*
   * Whether this deployment writes answers or extracts them. `/readiness`
   * says which answerer the server started with, so the drawer asks it the
   * first time it opens; every reply carries the flag as well, and a reply
   * saying "generated" wins. Until one of them has said "extractive", the
   * claim is the cautious one: telling a reader they are hearing the book when
   * they are hearing a model is the failure this label exists to prevent.
   */
  const [serverExtracts, setServerExtracts] = useState<boolean | null>(null);
  const generated = turns.some((turn) => turn.answer?.generated) || serverExtracts !== true;

  const drawerId = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    toggle.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  useEffect(() => {
    if (!open || serverExtracts !== null) return;
    let cancelled = false;
    api
      .readiness()
      .then((ready) => {
        if (!cancelled) setServerExtracts(ready.answers === "extractive");
      })
      // Unknown stays unknown, and the cautious claim stays up.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api, open, serverExtracts]);

  useEffect(() => {
    if (!open) return;
    // After paint, or the field does not exist yet to receive focus.
    const timer = window.setTimeout(() => field.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  // Keep the newest exchange in view. The log scrolls, not the page.
  useEffect(() => {
    if (turns.length === 0) return;
    const box = log.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [turns]);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        alert(strings.questionRequired);
        field.current?.focus();
        return;
      }
      // The selection is context for the reader, and part of what is sent: the
      // retriever has no idea what is on screen unless the question says so.
      const sent = selection ? `${selection}\n\n${trimmed}` : trimmed;
      const id = `${Date.now()}-${turns.length}`;
      // The recent conversation, so a follow-up such as "and the list of them?"
      // means something. Failed exchanges are left out: an error is not
      // something the reader was told about the book. The server bounds it
      // too; this keeps what is sent small in the first place.
      const history: Exchange[] = turns
        .filter((turn) => turn.answer !== null)
        .slice(-HISTORY_LIMIT)
        .map((turn) => ({ question: turn.question, answer: turn.answer?.answer ?? null }));

      setAsking(true);
      setQuestion("");
      setTurns((previous) => [...previous, { id, question: trimmed, answer: null, error: null }]);

      try {
        const answer = await api.askQuestion(documentId, sent, history);
        setTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, answer } : turn)),
        );
        say(answer.abstained ? strings.studyAbstainedHeading : strings.answerFound);
      } catch (cause) {
        const message =
          cause instanceof ApiError ? messageFor(cause.kind, strings) : strings.errorServer;
        setTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, error: message } : turn)),
        );
        alert(message);
      } finally {
        setAsking(false);
        onClearSelection();
      }
    },
    [alert, api, documentId, onClearSelection, say, selection, strings, turns],
  );

  const openCitation = useCallback(
    (segmentId: string | undefined, citationPage: number) => {
      if (!segmentId) return;
      if (onOpenCitation(segmentId)) {
        say(strings.citationOpened);
        return;
      }
      // Not on this page. Go there; the reader can then hear it.
      if (citationPage !== pageIndex) {
        onGoToPage(citationPage, segmentId);
        say(strings.citationOpened);
      } else {
        say(strings.citationUnavailable);
      }
    },
    [
      onGoToPage,
      onOpenCitation,
      pageIndex,
      say,
      strings.citationOpened,
      strings.citationUnavailable,
    ],
  );

  return (
    <>
      <button
        ref={toggle}
        type="button"
        className="assistant-fab btn btn-primary"
        aria-expanded={open}
        aria-controls={drawerId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <AskIcon />
        <span className="assistant-fab-label">{strings.assistantToggle}</span>
      </button>

      <aside
        ref={panel}
        id={drawerId}
        className="assistant"
        data-open={open}
        hidden={!open}
        aria-label={strings.assistantHeading}
        style={{ "--assistant-width": `${preferences.assistantWidth}rem` } as React.CSSProperties}
      >
        <AssistantEdge panel={panel} />
        <header className="assistant-head">
          <div>
            <h2>{strings.assistantHeading}</h2>
            {/* Which book, always. An answer grounded in the wrong document is
                the failure this label exists to make visible. */}
            <p className="hint">{strings.assistantFor(bookTitle)}</p>
          </div>
          <div className="assistant-head-tools">
            {turns.length > 0 ? (
              <button
                type="button"
                className="btn btn-quiet btn-sm"
                onClick={() => {
                  setTurns([]);
                  say(strings.assistantCleared);
                  field.current?.focus();
                }}
              >
                {strings.assistantClear}
              </button>
            ) : null}
            <button type="button" className="btn btn-quiet btn-sm" onClick={close}>
              {strings.assistantMinimise}
            </button>
          </div>
        </header>

        {/*
         * Said plainly, at the top, not in a footnote. Which sentence appears
         * depends on what the server is configured to do (see `generated`
         * above): the conservative claim until the server says otherwise.
         */}
        <p className="notice assistant-honesty" data-generated={generated}>
          {generated ? strings.assistantGenerated : strings.assistantExtractive}
        </p>

        <div
          className="assistant-log"
          ref={log}
          aria-live="polite"
          aria-atomic="false"
          aria-label={strings.conversationLabel}
        >
          {turns.length === 0 ? <p className="hint">{strings.assistantEmpty}</p> : null}

          {turns.map((turn) => (
            <article key={turn.id} className="turn">
              <p className="turn-question">
                <span className="turn-who">{strings.assistantYou}</span>
                <Typed text={turn.question} />
              </p>

              {turn.error ? (
                <p className="notice notice-bad">{turn.error}</p>
              ) : turn.answer === null ? (
                <p className="hint" aria-busy="true">
                  {strings.answering}
                </p>
              ) : turn.answer.abstained ? (
                <div className="notice notice-warn">
                  <h3>{strings.studyAbstainedHeading}</h3>
                  <p>{strings.studyAbstainedBody}</p>
                </div>
              ) : (
                <div className="turn-answer" data-generated={turn.answer.generated}>
                  <span className="turn-who">
                    {turn.answer.generated ? strings.answerFromAi : strings.answerFromBook}
                  </span>
                  <blockquote lang="si">{turn.answer.answer}</blockquote>

                  {turn.answer.citations.length > 0 ? (
                    <ol className="citations">
                      {turn.answer.citations.map((citation) => {
                        const label = citation.page_label ?? String(citation.page_index + 1);
                        const segmentId = citation.segment_ids[0];
                        return (
                          <li key={citation.passage_id}>
                            <button
                              type="button"
                              className="citation"
                              onClick={() => openCitation(segmentId, citation.page_index)}
                            >
                              <span className="citation-place latin">
                                {strings.citationPage(label)}
                              </span>
                              {citation.section ? (
                                <span className="citation-section">
                                  <Quoted
                                    format={strings.citationSection}
                                    text={citation.section}
                                  />
                                </span>
                              ) : null}
                              <span className="citation-quote" lang="si">
                                {citation.quote}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ol>
                  ) : null}
                </div>
              )}
            </article>
          ))}
        </div>

        {selection ? (
          <div className="assistant-selection">
            <p>
              <span className="turn-who">{strings.assistantSelectionLabel}</span>
              <q>{selection}</q>
            </p>
            <button type="button" className="btn btn-quiet btn-sm" onClick={onClearSelection}>
              {strings.assistantSelectionClear}
            </button>
          </div>
        ) : null}

        <form
          className="assistant-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!asking) void ask(question);
          }}
        >
          <label htmlFor={`${drawerId}-q`} className="visually-hidden">
            {strings.questionLabel}
          </label>
          <textarea
            id={`${drawerId}-q`}
            ref={field}
            value={question}
            rows={2}
            maxLength={500}
            placeholder={strings.questionPlaceholder}
            readOnly={asking}
            onChange={(event) => setQuestion(event.target.value)}
          />
          {/* Busy, not disabled, while an answer is on its way: disabling the
              button that has focus drops focus to <body>. */}
          <button className="btn btn-primary" type="submit" aria-disabled={asking || undefined}>
            {asking ? strings.answering : strings.assistantAsk}
          </button>
        </form>
      </aside>
    </>
  );
}

function AskIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 5.5h16v11H10l-5 4v-4H4v-11Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
