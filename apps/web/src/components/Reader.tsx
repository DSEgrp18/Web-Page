"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { AssistantDrawer } from "@/components/AssistantDrawer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { PdfPanel } from "@/components/PdfPanel";
import { PlayerBar } from "@/components/PlayerBar";
import { usePreferences } from "@/components/PreferencesProvider";
import { ReadingPanel } from "@/components/ReadingPanel";
import { useReader } from "@/components/ReaderProvider";
import { SplitView } from "@/components/SplitView";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { Bookmark, DocumentDetail, Page, Progress } from "@/lib/types";
import { usePlayer } from "@/lib/usePlayer";

type Side = "original" | "reading";

/**
 * The reading workspace: the printed page on one side, the words on the other.
 *
 * ## Why two panels rather than one
 *
 * The extracted text is what can be narrated, searched, and quoted; the
 * original page is what has the diagram, the table, and the layout that tells a
 * sighted student which paragraph goes with which figure. Neither is sufficient
 * and neither replaces the other, so both are on screen and kept on the same
 * page by default.
 *
 * Sync is a *default*, not a rule. Somebody comparing a figure on page 12 with
 * the text on page 13 has a real reason to break it, so the toggle is there and
 * it says which state it is in rather than being an icon to guess at.
 *
 * ## At phone width they become tabs
 *
 * Two 190px columns are two unusable columns. Below 900px the same two panels
 * become tabs, and the page and playback survive switching between them —
 * which is the part that is easy to get wrong, because remounting the panel
 * would restart both.
 *
 * ## Nothing ever starts speaking by itself
 *
 * CLAUDE.md forbids narration on load, and everything that looks like it might
 * — a bookmark link, a resumed position, a citation — goes through `cue`, which
 * selects a sentence without playing it.
 */
export function Reader({
  documentId,
  bookmarkSegmentId,
}: {
  documentId: string;
  /** From a bookmarks link; it is cued but never played automatically. */
  bookmarkSegmentId?: string;
}) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const { preferences, set } = usePreferences();

  const [book, setBook] = useState<DocumentDetail | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pdfPageIndex, setPdfPageIndex] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  /** The page index the last fetch settled on, successfully or not. */
  const [settledIndex, setSettledIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Progress | null>(null);
  const [bookmarkSaving, setBookmarkSaving] = useState(false);
  const [undoBookmark, setUndoBookmark] = useState<Bookmark | null>(null);

  const [collapsed, setCollapsed] = useState<"start" | "end" | null>(null);
  const [tab, setTab] = useState<Side>("reading");
  const [selection, setSelection] = useState("");

  const headingRef = useRef<HTMLHeadingElement>(null);
  /** Focus is moved on navigation, but never on arrival. */
  const navigated = useRef(false);
  const announcedPlaceholder = useRef(false);
  const cuedBookmark = useRef<string | null>(null);

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
        if (bookmarkSegmentId) {
          const segment = await api.getSegment(documentId, bookmarkSegmentId);
          if (!cancelled) {
            setPageIndex(segment.page_index);
            setPdfPageIndex(segment.page_index);
          }
          return;
        }
        const progress = await api.getProgress(documentId);
        if (cancelled) return;
        setSaved(progress);
        // Progress records a sentence, not a page. Asking the API which page it
        // is on beats parsing the id, which would tie the interface to a format
        // the pipeline is free to change.
        const segment = await api.getSegment(documentId, progress.segment_id);
        if (!cancelled) {
          setPageIndex(segment.page_index);
          setPdfPageIndex(segment.page_index);
        }
      } catch (cause) {
        // No saved position, or the sentence is gone after a reprocessing.
        // Either way the reader starts at the beginning.
        if (!(cause instanceof ApiError && cause.kind === "not_found")) {
          if (!cancelled) fail(cause);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, documentId, bookmarkSegmentId, fail]);

  // -- the current page --------------------------------------------------

  // Derived, not stored: loading is true exactly when the page being shown is
  // not the page being asked for. A separate flag is one more thing that can
  // disagree with reality.
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
    // is already reading. Moving it after "next page" is what tells the reader
    // the page actually changed.
    if (navigated.current) headingRef.current?.focus();
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

  // A bookmark opens the right page and identifies its sentence, but never
  // starts speaking. Separate from the page fetch so the player only receives
  // an id it can resolve on the page in front of it.
  useEffect(() => {
    if (
      !bookmarkSegmentId ||
      cuedBookmark.current === bookmarkSegmentId ||
      !segments.some((segment) => segment.segment_id === bookmarkSegmentId)
    ) {
      return;
    }
    cuedBookmark.current = bookmarkSegmentId;
    player.cue(bookmarkSegmentId, 0, false);
  }, [bookmarkSegmentId, player, segments]);

  useEffect(() => {
    if (!undoBookmark) return;
    const timer = window.setTimeout(() => setUndoBookmark(null), 8000);
    return () => window.clearTimeout(timer);
  }, [undoBookmark]);

  useEffect(() => {
    if (player.realModel !== false || announcedPlaceholder.current) return;
    announcedPlaceholder.current = true;
    // Said once, out loud, the first time a tone plays. A listener cannot tell
    // a placeholder from speech they were not expecting.
    say(strings.placeholderAudio);
  }, [player.realModel, say]);

  // -- navigation --------------------------------------------------------

  const goToPage = useCallback(
    (index: number) => {
      if (!book || index < 0 || index >= book.page_count) return;
      navigated.current = true;
      setPageIndex(index);
      if (preferences.syncPages) setPdfPageIndex(index);
    },
    [book, preferences.syncPages],
  );

  const goToPdfPage = useCallback(
    (index: number) => {
      if (!book || index < 0 || index >= book.page_count) return;
      setPdfPageIndex(index);
      if (preferences.syncPages) {
        navigated.current = true;
        setPageIndex(index);
      }
    },
    [book, preferences.syncPages],
  );

  // Turning sync back on brings the panels together rather than leaving them
  // apart until the next page turn, which would look like the toggle did
  // nothing.
  const toggleSync = useCallback(() => {
    const next = !preferences.syncPages;
    set("syncPages", next);
    if (next && pdfPageIndex !== pageIndex) setPdfPageIndex(pageIndex);
  }, [preferences.syncPages, set, pdfPageIndex, pageIndex]);

  /**
   * Move to a cited sentence without leaving the page.
   *
   * The panel's whole advantage over a separate study screen: checking where an
   * answer came from costs nothing. Returns false when the sentence is not on
   * this page — a citation into text that has since been re-extracted — because
   * appearing to do nothing is worse than saying so.
   */
  const openCitation = useCallback(
    (segmentId: string) => {
      if (!segments.some((segment) => segment.segment_id === segmentId)) return false;
      // Cued, never played. CLAUDE.md forbids narration starting by itself.
      player.cue(segmentId, 0, false);
      return true;
    },
    [player, segments],
  );

  // -- bookmarks ---------------------------------------------------------

  const currentIndex = segments.findIndex((segment) => segment.segment_id === player.currentId);
  const bookmarkLabel =
    currentIndex >= 0
      ? strings.bookmarkSentence(pageIndex + 1, currentIndex + 1)
      : strings.bookmarkCurrentSentence;

  const addBookmark = useCallback(async () => {
    if (!player.currentId) return;
    setBookmarkSaving(true);
    try {
      // The API updates an existing bookmark at the same sentence. Only a new
      // record gets Undo: deleting after an update would discard a place the
      // reader had already kept.
      const existing = await api.listBookmarks(documentId);
      const already = existing.some((bookmark) => bookmark.segment_id === player.currentId);
      const bookmark = await api.addBookmark(documentId, player.currentId);
      say(already ? strings.bookmarkUpdated : `${strings.bookmarkSaved} ${strings.undo}`);
      setUndoBookmark(already ? null : bookmark);
    } catch (cause) {
      fail(cause);
    } finally {
      setBookmarkSaving(false);
    }
  }, [api, documentId, fail, player.currentId, say]);

  const undoSavedBookmark = useCallback(async () => {
    if (!undoBookmark) return;
    try {
      await api.deleteBookmark(documentId, undoBookmark.bookmark_id);
      setUndoBookmark(null);
      say(strings.bookmarkRemoved);
    } catch (cause) {
      fail(cause);
    }
  }, [api, documentId, fail, say, undoBookmark]);

  // -- selection, for asking about a passage ------------------------------

  const captureSelection = useCallback(() => {
    const text = window.getSelection?.()?.toString().trim() ?? "";
    // Only meaningful selections. A stray click selects nothing, and a single
    // character is not a question.
    if (text.length >= 3) setSelection(text.slice(0, 500));
  }, []);

  // -- render ------------------------------------------------------------

  if (error && !book) {
    return <ErrorNotice message={error} onRetry={() => window.location.reload()} />;
  }
  if (!book) {
    return (
      <p className="hint workspace-loading" aria-busy="true">
        {strings.pageLoading}
      </p>
    );
  }

  const title = book.title?.trim() || book.filename;
  const resumable =
    saved && segments.some((segment) => segment.segment_id === saved.segment_id) ? saved : null;

  const pdfPanel = (
    <PdfPanel
      documentId={documentId}
      pageIndex={pdfPageIndex}
      pageCount={book.page_count}
      onPageChange={goToPdfPage}
    />
  );

  const readingPanel = (
    <>
      {resumable ? (
        <div className="resume-strip">
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => player.cue(resumable.segment_id, resumable.offset_seconds, true)}
          >
            {strings.resume}
          </button>
          {resumable.stale ? <span className="hint">{strings.resumeStale}</span> : null}
        </div>
      ) : null}
      <ReadingPanel
        key={pageIndex}
        page={page}
        segments={segments}
        loading={loading}
        currentId={player.currentId}
        playing={player.status === "playing"}
        onPlayIndex={player.playAt}
        documentNotes={book.notes}
      />
      <div className="reading-pager">
        <button
          type="button"
          className="btn btn-quiet btn-sm"
          onClick={() => goToPage(pageIndex - 1)}
          disabled={loading || pageIndex <= 0}
        >
          {strings.previousPage}
        </button>
        <span className="hint latin">{strings.ofPages(pageIndex + 1, book.page_count)}</span>
        <button
          type="button"
          className="btn btn-quiet btn-sm"
          onClick={() => goToPage(pageIndex + 1)}
          disabled={loading || pageIndex >= book.page_count - 1}
        >
          {strings.nextPage}
        </button>
      </div>
    </>
  );

  return (
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- mouseup/keyup here only *observe* a selection the reader made with the platform's own text selection. There is no interaction to trigger and nothing to give keyboard access to; the handlers read window.getSelection() and nothing else.
    <div className="workspace" onMouseUp={captureSelection} onKeyUp={captureSelection}>
      <header className="workspace-bar">
        <Link className="btn btn-quiet btn-sm" href="/">
          <span aria-hidden="true">‹ </span>
          {strings.backToLibrary}
        </Link>

        <h1 ref={headingRef} tabIndex={-1} className="workspace-title">
          {title}
        </h1>

        <div className="workspace-tools">
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            aria-pressed={preferences.syncPages}
            onClick={toggleSync}
          >
            <LinkIcon broken={!preferences.syncPages} />
            {preferences.syncPages ? strings.syncPages : strings.syncPagesOff}
          </button>

          <button
            type="button"
            className="btn btn-quiet btn-sm"
            aria-pressed={collapsed === "start"}
            onClick={() => setCollapsed(collapsed === "start" ? null : "start")}
          >
            {collapsed === "start" ? strings.restoreSplit : strings.expandOriginal}
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            aria-pressed={collapsed === "end"}
            onClick={() => setCollapsed(collapsed === "end" ? null : "end")}
          >
            {collapsed === "end" ? strings.restoreSplit : strings.expandReading}
          </button>
        </div>
      </header>

      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      {/* Tabs at phone width. Both panels stay mounted — swapping them out
          would restart the PDF and the playback along with it. */}
      <div className="workspace-tabs" role="tablist" aria-label={strings.workspaceTabs}>
        {(["original", "reading"] as Side[]).map((side) => (
          <button
            key={side}
            type="button"
            role="tab"
            id={`tab-${side}`}
            aria-selected={tab === side}
            aria-controls={`panel-${side}`}
            className="workspace-tab"
            onClick={() => setTab(side)}
          >
            {side === "original" ? strings.originalPanel : strings.readingPanel}
          </button>
        ))}
      </div>

      <div className="workspace-body" data-tab={tab}>
        <SplitView
          percent={preferences.splitPercent}
          onPercent={(next) => set("splitPercent", next)}
          collapsed={collapsed}
          startLabel={strings.originalPanel}
          endLabel={strings.readingPanel}
          start={
            <div
              id="panel-original"
              role="tabpanel"
              aria-labelledby="tab-original"
              className="pane"
            >
              {pdfPanel}
            </div>
          }
          end={
            <div id="panel-reading" role="tabpanel" aria-labelledby="tab-reading" className="pane">
              {readingPanel}
            </div>
          }
        />
      </div>

      {undoBookmark ? (
        <div className="bookmark-toast" role="group" aria-label={strings.bookmarksHeading}>
          <p>{strings.bookmarkSaved}</p>
          <button type="button" className="btn btn-sm" onClick={() => void undoSavedBookmark()}>
            {strings.undoBookmark}
          </button>
        </div>
      ) : null}

      <PlayerBar
        player={player}
        disabled={segments.length === 0}
        position={currentIndex + 1}
        total={segments.length}
        bookmarkLabel={bookmarkLabel}
        bookmarkSaving={bookmarkSaving}
        onBookmark={() => void addBookmark()}
      />

      <AssistantDrawer
        documentId={documentId}
        bookTitle={title}
        pageIndex={pageIndex}
        selection={selection}
        onClearSelection={() => setSelection("")}
        onOpenCitation={openCitation}
        onGoToPage={goToPage}
      />
    </div>
  );
}

function LinkIcon({ broken }: { broken: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M10 14a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7L11.4 6.9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M14 10a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 0 0 5.7 5.7l1.4-1.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      {broken ? (
        <path d="M4 20 20 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      ) : null}
    </svg>
  );
}
