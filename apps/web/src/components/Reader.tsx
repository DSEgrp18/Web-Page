"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { DocumentDetail, Page, Progress } from "@/lib/types";
import { usePlayer } from "@/lib/usePlayer";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/**
 * The reading screen: one page of sentences, and the controls to hear them.
 *
 * Two decisions here are about screen readers specifically.
 *
 * **Each sentence is a button whose name is the sentence.** Navigating by
 * button — the fastest way through a page in NVDA and TalkBack — then reads the
 * text and offers to play it in one stop. The alternative, a small "play" icon
 * beside each sentence, produces a list of forty identically-named buttons.
 *
 * **There are no single-key shortcuts.** `p`, `n`, `space` and friends collide
 * with NVDA's browse-mode quick navigation, where single letters jump between
 * elements. Every control here is a real button, reachable by Tab and by
 * element navigation. Shortcuts can be added later, scoped to the player and
 * tested with a real screen reader — not guessed at now.
 */
export function Reader({ documentId }: { documentId: string }) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();

  const [book, setBook] = useState<DocumentDetail | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  /** The page index the last fetch settled on, successfully or not. */
  const [settledIndex, setSettledIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Progress | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  /** Focus is moved on navigation, but not on arrival. */
  const navigatedRef = useRef(false);
  const announcedPlaceholderRef = useRef(false);

  const fail = useCallback(
    (cause: unknown) => {
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
      setError(message);
      alert(message);
    },
    [alert],
  );

  // -- the book, and where the reader left off ---------------------------

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const detail = await api.getDocument(documentId);
        if (cancelled) return;
        setBook(detail);
      } catch (cause) {
        if (!cancelled) fail(cause);
        return;
      }
      try {
        const progress = await api.getProgress(documentId);
        if (cancelled) return;
        setSaved(progress);
        // Progress records a sentence, not a page. Asking the API which page
        // that sentence is on beats parsing the id, which would tie the
        // interface to a format the pipeline is free to change.
        const segment = await api.getSegment(documentId, progress.segment_id);
        if (!cancelled) setPageIndex(segment.page_index);
      } catch (cause) {
        // No saved position, or the sentence no longer exists after a
        // reprocessing. Either way the reader starts at the beginning.
        if (!(cause instanceof ApiError && cause.kind === "not_found")) {
          if (!cancelled) fail(cause);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, documentId, fail]);

  // -- the current page --------------------------------------------------

  // "Loading" is derived, not stored: it is true exactly when the page being
  // shown is not the page being asked for. A separate flag is one more thing
  // that can disagree with reality.
  const loading = settledIndex !== pageIndex;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await api.getPage(documentId, pageIndex);
        if (cancelled) return;
        setPage(loaded);
        setError(null);
      } catch (cause) {
        if (!cancelled) fail(cause);
      } finally {
        if (!cancelled) setSettledIndex(pageIndex);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, documentId, pageIndex, fail]);

  useEffect(() => {
    if (!page) return;
    say(
      `${strings.pageWord} ${page.page_index + 1}. ${strings.sentenceCount(page.segments.length)}`,
    );
    // Moving focus on arrival would yank a screen reader out of the heading it
    // is already reading. Moving it after the reader pressed "next page" is
    // what tells them the page actually changed.
    if (navigatedRef.current) headingRef.current?.focus();
  }, [page, say]);

  // -- playback ----------------------------------------------------------

  const segments = useMemo(() => page?.segments ?? [], [page]);

  const onPosition = useCallback(
    (segmentId: string, offsetSeconds: number) => {
      // Losing a saved position is a small harm; interrupting the reader to
      // report it is a larger one. It is retried the next time they pause.
      void api.saveProgress(documentId, segmentId, offsetSeconds).catch(() => {});
    },
    [api, documentId],
  );

  const player = usePlayer({ api, documentId, segments, onPosition, onError: fail });
  const { stop } = player;

  // A new page is a new queue. Anything still playing belongs to the old one.
  useEffect(() => {
    stop();
  }, [pageIndex, stop]);

  useEffect(() => {
    if (player.realModel !== false || announcedPlaceholderRef.current) return;
    announcedPlaceholderRef.current = true;
    // Said once, out loud, the first time a tone plays. A listener cannot tell
    // a placeholder from speech they were not expecting.
    say(strings.placeholderAudio);
  }, [player.realModel, say]);

  // Follow-reading (#29): while playing, keep the current sentence in view for
  // low-vision readers at high zoom. Never steal focus — that would yank a
  // screen-reader cursor every sentence. Setting UI lands in #30; default on.
  // TODO(#30): honour the reading-settings switch when that screen exists.
  const followReading = true;
  useEffect(() => {
    if (!followReading || player.status !== "playing" || !player.currentId) return;
    const el = document.querySelector<HTMLElement>(`.sentence[data-current="true"] .sentence-text`);
    if (!el) return;
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
  }, [followReading, player.status, player.currentId]);

  const goToPage = useCallback(
    (index: number) => {
      if (!book || index < 0 || index >= book.page_count || index === pageIndex) return;
      navigatedRef.current = true;
      setPageIndex(index);
    },
    [book, pageIndex],
  );

  if (error && !book) {
    return <ErrorNotice message={error} onRetry={() => window.location.reload()} />;
  }
  if (!book) return <p>{strings.pageLoading}</p>;

  const resumable =
    saved && segments.some((segment) => segment.segment_id === saved.segment_id) ? saved : null;

  return (
    <>
      <p>
        <Link href="/">{strings.backToLibrary}</Link>
      </p>

      <h2 ref={headingRef} tabIndex={-1}>
        {book.filename} — {strings.pageWord} {pageIndex + 1}
        {page?.page_label ? ` (${strings.printedPage} ${page.page_label})` : null}
      </h2>
      <p className="hint">{strings.ofPages(pageIndex + 1, book.page_count)}</p>

      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      <PageNavigation
        key={pageIndex}
        pageIndex={pageIndex}
        pageCount={book.page_count}
        onGo={goToPage}
        disabled={loading}
      />

      {book.notes.length > 0 ? (
        <div className="notice">
          <h3>{strings.documentNotesHeading}</h3>
          <ul>
            {book.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {page ? <PageNotes page={page} /> : null}

      {resumable ? (
        <p className="row">
          <button
            type="button"
            onClick={() => player.cue(resumable.segment_id, resumable.offset_seconds, true)}
          >
            {strings.resume}
          </button>
          {resumable.stale ? <span className="hint">{strings.resumeStale}</span> : null}
        </p>
      ) : null}

      <section aria-labelledby="sentences-heading">
        <h3 id="sentences-heading">
          {strings.sentencesHeading}
          <span className="hint"> · {strings.sentenceCount(segments.length)}</span>
        </h3>
        {loading ? (
          <p>{strings.pageLoading}</p>
        ) : segments.length === 0 ? (
          <p>{strings.noSentences}</p>
        ) : (
          <ol className="sentences">
            {segments.map((segment, index) => {
              const current = player.currentId === segment.segment_id;
              return (
                <li key={segment.segment_id} className="sentence" data-current={current}>
                  <button
                    type="button"
                    className="sentence-text"
                    aria-current={current ? "true" : undefined}
                    onClick={() => player.playAt(index)}
                  >
                    {segment.display_text}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {player.realModel === false ? (
        <div className="notice">
          <h3>{strings.placeholderAudioHeading}</h3>
          <p>{strings.placeholderAudio}</p>
        </div>
      ) : null}

      <PlayerBar player={player} disabled={segments.length === 0} />
    </>
  );
}

function PageNavigation({
  pageIndex,
  pageCount,
  onGo,
  disabled,
}: {
  pageIndex: number;
  pageCount: number;
  onGo: (index: number) => void;
  disabled: boolean;
}) {
  const inputId = useId();
  // Remounted by its `key` whenever the page changes, which is what resets the
  // field. An effect that copied the prop into state would render the old
  // number once first, and a screen reader would read it.
  const [value, setValue] = useState(String(pageIndex + 1));

  return (
    <nav aria-label={strings.goToPage}>
      <form
        className="row"
        onSubmit={(event) => {
          event.preventDefault();
          const requested = Number.parseInt(value, 10);
          if (Number.isFinite(requested)) onGo(requested - 1);
        }}
      >
        <button
          type="button"
          onClick={() => onGo(pageIndex - 1)}
          disabled={disabled || pageIndex <= 0}
        >
          {strings.previousPage}
        </button>
        <label htmlFor={inputId} className="visually-hidden">
          {strings.goToPage}
        </label>
        <input
          id={inputId}
          type="number"
          inputMode="numeric"
          min={1}
          max={pageCount}
          value={value}
          style={{ width: "6rem" }}
          onChange={(event) => setValue(event.target.value)}
        />
        <button type="submit" disabled={disabled}>
          {strings.goToPageSubmit}
        </button>
        <button
          type="button"
          onClick={() => onGo(pageIndex + 1)}
          disabled={disabled || pageIndex >= pageCount - 1}
        >
          {strings.nextPage}
        </button>
      </form>
    </nav>
  );
}

/**
 * What this page loses, said in the page rather than hidden behind a warning
 * icon. CLAUDE.md forbids claiming full accessibility when content has not been
 * handled; this is where that promise is kept or broken.
 */
function PageNotes({ page }: { page: Page }) {
  const messages: string[] = [];
  if (page.quality === "undecodable") messages.push(strings.qualityUndecodable);
  else if (page.quality === "needs_review") messages.push(strings.qualityNeedsReview);
  if (page.kind === "image") messages.push(strings.kindImage);
  for (const note of page.notes) messages.push(note);

  if (messages.length === 0) return null;
  return (
    <div className="notice">
      <h3>{strings.pageNotesHeading}</h3>
      <ul>
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}

function PlayerBar({
  player,
  disabled,
}: {
  player: ReturnType<typeof usePlayer>;
  disabled: boolean;
}) {
  const speedId = useId();
  const playing = player.status === "playing";
  const busy = player.status === "loading";

  return (
    <div className="player">
      {/* A group, not a toolbar: `role="toolbar"` takes over the arrow keys,
          which a screen reader user is already using to move through the text. */}
      <div className="row" role="group" aria-label={strings.sentencesHeading}>
        <button type="button" onClick={player.previous} disabled={disabled}>
          {strings.previousSentence}
        </button>
        <button className="primary" type="button" onClick={player.toggle} disabled={disabled}>
          {busy ? strings.loadingAudio : playing ? strings.pause : strings.play}
        </button>
        <button type="button" onClick={player.next} disabled={disabled}>
          {strings.nextSentence}
        </button>
        <button type="button" onClick={player.stop} disabled={disabled || player.status === "idle"}>
          {strings.stop}
        </button>
        <label htmlFor={speedId} className="visually-hidden">
          {strings.speed}
        </label>
        <select
          id={speedId}
          value={String(player.rate)}
          onChange={(event) => player.setRate(Number(event.target.value))}
        >
          {SPEEDS.map((speed) => (
            <option key={speed} value={String(speed)}>
              {strings.speed} {speed}×
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
