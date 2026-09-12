"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { StudyAnswer } from "@/lib/types";

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
  onGoToPage: (index: number) => void;
}) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();

  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [asking, setAsking] = useState(false);

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

      setAsking(true);
      setQuestion("");
      setTurns((previous) => [...previous, { id, question: trimmed, answer: null, error: null }]);

      try {
        const answer = await api.askQuestion(documentId, sent);
        setTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, answer } : turn)),
        );
        say(answer.abstained ? strings.studyAbstainedHeading : strings.answerFound);
      } catch (cause) {
        const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
        setTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, error: message } : turn)),
        );
        alert(message);
      } finally {
        setAsking(false);
        onClearSelection();
      }
    },
    [alert, api, documentId, onClearSelection, say, selection, turns.length],
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
        onGoToPage(citationPage);
        say(strings.citationOpened);
      } else {
        say(strings.citationUnavailable);
      }
    },
    [onGoToPage, onOpenCitation, pageIndex, say],
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
        id={drawerId}
        className="assistant"
        data-open={open}
        hidden={!open}
        aria-label={strings.assistantHeading}
      >
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
         * Said plainly, at the top, not in a footnote: these answers are the
         * book's own sentences. A reader who believes they are getting an
         * explanation will read them as one.
         */}
        <p className="notice assistant-honesty">{strings.assistantExtractive}</p>

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
                {turn.question}
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
                <div className="turn-answer">
                  <span className="turn-who">{strings.assistantAnswer}</span>
                  <blockquote>{turn.answer.answer}</blockquote>

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
                                  {strings.citationSection(citation.section)}
                                </span>
                              ) : null}
                              <span className="citation-quote">{citation.quote}</span>
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
            void ask(question);
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
            disabled={asking}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={asking}>
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
