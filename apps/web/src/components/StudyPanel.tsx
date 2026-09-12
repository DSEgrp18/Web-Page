"use client";

import { FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { StudyAnswer } from "@/lib/types";

/**
 * Asking a question without losing your place.
 *
 * The same study mode as `/documents/[id]/study`, beside the book rather than
 * instead of it. The page is kept — a reader who wants the whole screen for a
 * question should have it — but the panel is what makes a citation useful:
 * `onOpenCitation` moves the reader to that sentence **in place**, so checking
 * where an answer came from does not cost the page you were on.
 *
 * Four decisions here are accessibility decisions, not layout ones.
 *
 * **A disclosure, not a dialog.** The panel does not trap focus or make the
 * book inert, because the book is the thing you are asking about and a reader
 * may well want to move through it while the panel is open. `aria-expanded` and
 * `aria-controls` on the toggle say what it does; Escape closes it.
 *
 * **Focus moves in, and comes back.** Opening puts focus in the question field,
 * because that is the only reason to open it. Closing returns focus to the
 * toggle rather than dropping it at the top of the document, which is what
 * makes the panel usable twice.
 *
 * **The answer arrives politely.** `aria-live="polite"` on the results region:
 * an answer that interrupts narration mid-sentence is worse than one that waits
 * for a gap. CLAUDE.md reserves assertive for urgent errors, and a study answer
 * is never urgent.
 *
 * **"Side" is a sighted word.** In the DOM the panel follows the sentences and
 * precedes nothing, so tab order matches reading order however it is painted.
 * Where it sits on screen is CSS.
 */
export function StudyPanel({
  documentId,
  onOpenCitation,
}: {
  documentId: string;
  /**
   * Move the reader to a cited sentence. Returns whether it could — a citation
   * into a page that has since changed cannot be honoured, and saying so is
   * better than appearing to do nothing.
   */
  onOpenCitation?: (segmentId: string) => boolean;
}) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const panelId = useId();

  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<StudyAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const toggleRef = useRef<HTMLButtonElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    // Back to where it was opened from. Without this, focus lands at the top of
    // the document and the reader has to walk back to their sentence.
    toggleRef.current?.focus();
  }, []);

  const toggle = useCallback(() => {
    setOpen((wasOpen) => {
      if (wasOpen) {
        toggleRef.current?.focus();
        return false;
      }
      // After paint, or the field does not exist to receive focus yet.
      window.setTimeout(() => questionRef.current?.focus(), 0);
      return true;
    });
  }, []);

  /*
   * Escape closes it, from anywhere.
   *
   * On the document rather than on the panel element: the panel is a region,
   * not a widget, and a key handler on a non-interactive element only fires
   * when focus is already inside it — which excludes the case that matters,
   * a reader who has tabbed back into the book and wants the panel gone.
   */
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  const fail = useCallback(
    (cause: unknown) => {
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
      setError(message);
      alert(message);
    },
    [alert],
  );

  const ask = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = question.trim();
      if (!trimmed) {
        setError(strings.questionRequired);
        alert(strings.questionRequired);
        questionRef.current?.focus();
        return;
      }
      setAsking(true);
      setError(null);
      setResult(null);
      try {
        const answer = await api.askQuestion(documentId, trimmed);
        setResult(answer);
        say(answer.abstained ? strings.studyAbstainedHeading : strings.answerFound);
      } catch (cause) {
        fail(cause);
      } finally {
        setAsking(false);
      }
    },
    [alert, api, documentId, fail, question, say],
  );

  const openCitation = useCallback(
    (segmentId: string | undefined) => {
      if (!segmentId || !onOpenCitation) return;
      const moved = onOpenCitation(segmentId);
      say(moved ? strings.citationOpened : strings.citationUnavailable);
    },
    [onOpenCitation, say],
  );

  return (
    <aside className="study-panel" data-open={open} aria-labelledby={`${panelId}-toggle`}>
      <button
        id={`${panelId}-toggle`}
        ref={toggleRef}
        type="button"
        className="study-panel-toggle"
        aria-expanded={open}
        aria-controls={`${panelId}-body`}
        onClick={toggle}
      >
        {strings.studyPanelToggle}
      </button>

      <div id={`${panelId}-body`} className="study-panel-body" hidden={!open}>
        <p className="hint">{strings.studyIntro}</p>

        {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

        <form onSubmit={(event) => void ask(event)}>
          <label htmlFor={`${panelId}-question`}>{strings.questionLabel}</label>
          <textarea
            id={`${panelId}-question`}
            ref={questionRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={strings.questionPlaceholder}
            maxLength={500}
            rows={3}
            disabled={asking}
          />
          <p className="hint">{strings.studyHonesty}</p>
          <div className="study-panel-actions">
            <button className="primary" type="submit" disabled={asking}>
              {asking ? strings.answering : strings.askQuestion}
            </button>
            <button type="button" onClick={close}>
              {strings.closePanel}
            </button>
          </div>
        </form>

        {/*
         * Polite, and always present in the DOM rather than mounted when an
         * answer arrives: a live region added at the same moment its content
         * appears is not reliably announced.
         */}
        <div className="study-panel-result" aria-live="polite" aria-atomic="false">
          {result?.abstained ? (
            <section className="notice study-abstained">
              <h3>{strings.studyAbstainedHeading}</h3>
              <p>{strings.studyAbstainedBody}</p>
            </section>
          ) : null}

          {result?.answer ? (
            <section className="study-result">
              <h3>{strings.answerHeading}</h3>
              <blockquote>{result.answer}</blockquote>

              {result.citations.length > 0 ? (
                <>
                  <h4>{strings.sourcesHeading}</h4>
                  <ol className="study-citations">
                    {result.citations.map((citation) => {
                      const page = citation.page_label ?? String(citation.page_index + 1);
                      const segmentId = citation.segment_ids[0];
                      return (
                        <li key={citation.passage_id} className="study-citation">
                          <p className="study-citation-place">
                            {strings.citationPage(page)}
                            {citation.section
                              ? ` · ${strings.citationSection(citation.section)}`
                              : null}
                          </p>
                          <p>{citation.quote}</p>
                          {segmentId && onOpenCitation ? (
                            <button type="button" onClick={() => openCitation(segmentId)}>
                              {strings.openCitation}
                            </button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ol>
                </>
              ) : null}
            </section>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
