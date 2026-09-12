"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { BookCover } from "@/components/BookCover";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { RenameDialog } from "@/components/RenameDialog";
import { UploadDialog } from "@/components/UploadDialog";
import {
  bookTitle,
  continueReading,
  isFinished,
  isReady,
  matchesQuery,
  onShelf,
  percentRead,
  sortBooks,
  type Order,
  type Shelf,
} from "@/lib/books";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { DocumentSummary } from "@/lib/types";

/** How often to ask whether a book has finished preparing. */
const POLL_MS = 1500;

const SHELVES: { id: Shelf; label: string }[] = [
  { id: "all", label: strings.filterAll },
  { id: "reading", label: strings.filterReading },
  { id: "finished", label: strings.filterFinished },
  { id: "processing", label: strings.filterProcessing },
];

const ORDERS: { id: Order; label: string }[] = [
  { id: "recent", label: strings.sortRecent },
  { id: "added", label: strings.sortAdded },
  { id: "title", label: strings.sortTitle },
];

/**
 * The landing screen and the reader's shelf, in one place.
 *
 * They are the same screen because they answer the same question at different
 * times. Somebody arriving for the first time needs to know what this is and
 * how to start; somebody returning needs the book they were reading, in one
 * click, above everything else. Splitting them would give the returning reader
 * a marketing page to scroll past every single time.
 *
 * So: the welcome is large and the only thing on screen when the shelf is
 * empty, and shrinks to a strip once there are books. "Continue reading" is
 * first when there is something to continue.
 */
export function Library() {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();

  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [shelf, setShelf] = useState<Shelf>("all");
  const [order, setOrder] = useState<Order>("recent");

  const [uploading, setUploading] = useState(false);
  const [renaming, setRenaming] = useState<DocumentSummary | null>(null);
  const [deleting, setDeleting] = useState<DocumentSummary | null>(null);

  const addButton = useRef<HTMLButtonElement>(null);
  const cardTrigger = useRef<HTMLElement | null>(null);
  const searchId = useId();
  const sortId = useId();

  /** Which books were still being prepared last time we looked. */
  const pending = useRef(new Set<string>());

  const apply = useCallback(
    (listed: DocumentSummary[]) => {
      setDocuments(listed);
      setError(null);
      // Announce the transition, never the poll. CLAUDE.md is explicit that
      // routine progress must not be narrated on every update: a book becoming
      // ready is news, "still working" every 1.5 seconds is not.
      const stillPending = new Set<string>();
      for (const book of listed) {
        if (!isReady(book)) stillPending.add(book.document_id);
        else if (pending.current.has(book.document_id)) say(strings.prepared);
      }
      pending.current = stillPending;
    },
    [say],
  );

  const fail = useCallback(
    (cause: unknown) => {
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
      setError(message);
      alert(message);
    },
    [alert],
  );

  const refresh = useCallback(async () => {
    try {
      apply(await api.listDocuments());
    } catch (cause) {
      fail(cause);
    }
  }, [api, apply, fail]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const listed = await api.listDocuments();
        if (!cancelled) apply(listed);
      } catch (cause) {
        if (!cancelled) fail(cause);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, apply, fail]);

  // Poll only while something is being prepared, and stop the moment nothing
  // is. An idle library makes no requests: this runs on a student's phone.
  const anyPending = (documents ?? []).some((book) => !isReady(book));
  useEffect(() => {
    if (!anyPending) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [anyPending, refresh]);

  const confirmDelete = useCallback(async () => {
    const book = deleting;
    setDeleting(null);
    if (!book) return;
    try {
      await api.deleteDocument(book.document_id);
      say(strings.deleted);
      await refresh();
    } catch (cause) {
      fail(cause);
    }
  }, [api, deleting, refresh, say, fail]);

  const saveName = useCallback(
    async (title: string) => {
      const book = renaming;
      setRenaming(null);
      if (!book) return;
      try {
        await api.renameDocument(book.document_id, title);
        say(strings.renamed);
        await refresh();
      } catch (cause) {
        fail(cause);
      }
    },
    [api, renaming, refresh, say, fail],
  );

  // Memoised because `documents ?? []` is a new array every render, which
  // would make both memos below recompute on every keystroke in the search box.
  const all = useMemo(() => documents ?? [], [documents]);
  const resume = useMemo(() => continueReading(all), [all]);
  const shown = useMemo(
    () =>
      sortBooks(
        all.filter((b) => onShelf(b, shelf) && matchesQuery(b, query)),
        order,
      ),
    [all, shelf, query, order],
  );

  const openUpload = () => setUploading(true);

  return (
    <div className="library">
      <Welcome compact={all.length > 0} onAdd={openUpload} addRef={addButton} />

      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      {documents === null ? (
        <p className="hint" aria-busy="true">
          {strings.pageLoading}
        </p>
      ) : all.length === 0 ? null : (
        <>
          {resume ? <ContinueCard book={resume} /> : null}

          <section className="shelf" aria-labelledby="shelf-heading">
            <div className="shelf-head">
              <h2 id="shelf-heading">{strings.browseBooks}</h2>
              <p className="hint">{strings.libraryCount(all.length)}</p>
            </div>

            <div className="shelf-controls">
              <div className="search">
                <label htmlFor={searchId} className="visually-hidden">
                  {strings.searchLibrary}
                </label>
                <SearchIcon />
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  placeholder={strings.searchLibraryPlaceholder}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>

              {/* A tab-like filter, but these are not tabs: they filter one
                  list rather than swapping panels, so they are radios. A
                  screen reader should say "2 of 4", not "tab". */}
              <fieldset className="shelf-filters">
                <legend className="visually-hidden">{strings.filterHeading}</legend>
                <div className="segmented">
                  {SHELVES.map((option) => (
                    <label key={option.id} className="segment">
                      <input
                        type="radio"
                        name="shelf"
                        value={option.id}
                        checked={shelf === option.id}
                        onChange={() => setShelf(option.id)}
                      />
                      <span>{option.label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="shelf-sort">
                <label htmlFor={sortId}>{strings.sortHeading}</label>
                <select
                  id={sortId}
                  value={order}
                  onChange={(event) => setOrder(event.target.value as Order)}
                >
                  {ORDERS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {shown.length === 0 ? (
              query.trim() ? (
                <div className="empty-note">
                  <h3>{strings.noResultsHeading}</h3>
                  <p>{strings.noResultsBody(query.trim())}</p>
                  <button className="btn" type="button" onClick={() => setQuery("")}>
                    {strings.clearSearch}
                  </button>
                </div>
              ) : (
                <p className="empty-note hint">{strings.noneInFilter}</p>
              )
            ) : (
              <ul className="book-grid">
                {shown.map((book) => (
                  <BookCard
                    key={book.document_id}
                    book={book}
                    onRename={(trigger) => {
                      cardTrigger.current = trigger;
                      setRenaming(book);
                    }}
                    onDelete={(trigger) => {
                      cardTrigger.current = trigger;
                      setDeleting(book);
                    }}
                  />
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <UploadDialog
        open={uploading}
        onClose={() => setUploading(false)}
        onUploaded={(created) => {
          pending.current.add(created.document_id);
          void refresh();
        }}
        returnFocusTo={addButton}
      />

      {/* Mounted only while open, and keyed by book: that is what lets the
          dialog initialise its field from the title directly instead of
          copying a prop into state in an effect. */}
      {renaming ? (
        <RenameDialog
          key={renaming.document_id}
          current={bookTitle(renaming)}
          onCancel={() => setRenaming(null)}
          onSave={(title) => void saveName(title)}
          returnFocusTo={cardTrigger}
        />
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        title={strings.deleteConfirmTitle}
        body={deleting ? strings.deleteConfirmBody(bookTitle(deleting)) : null}
        cancelLabel={strings.deleteConfirmCancel}
        confirmLabel={strings.deleteConfirmAction}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
        returnFocusRef={cardTrigger}
      />
    </div>
  );
}

/**
 * The welcome.
 *
 * Large and alone on an empty shelf; a strip once there are books. Same
 * content either way, so a returning reader is not shown a different product
 * from the one they signed up to — just less of it.
 */
function Welcome({
  compact,
  onAdd,
  addRef,
}: {
  compact: boolean;
  onAdd: () => void;
  addRef: React.RefObject<HTMLButtonElement | null>;
}) {
  return (
    <section className="welcome" data-compact={compact} aria-labelledby="welcome-heading">
      <div className="welcome-copy">
        <h1 id="welcome-heading">{compact ? strings.libraryHeading : strings.welcomeHeading}</h1>
        {compact ? null : <p className="welcome-body">{strings.welcomeBody}</p>}
        <div className="welcome-actions">
          <button ref={addRef} className="btn btn-primary" type="button" onClick={onAdd}>
            <PlusIcon />
            {strings.addBook}
          </button>
          {compact ? null : <p className="hint">{strings.welcomeSecondary}</p>}
        </div>
      </div>
      {compact ? null : (
        <img
          className="welcome-art"
          src="/brand/swara-book.webp"
          alt=""
          width={700}
          height={450}
          loading="eager"
          decoding="async"
        />
      )}
    </section>
  );
}

function ContinueCard({ book }: { book: DocumentSummary }) {
  const percent = percentRead(book);
  const title = bookTitle(book);
  return (
    <section className="continue card" aria-labelledby="continue-heading">
      <BookCover documentId={book.document_id} ready={isReady(book)} />
      <div className="continue-copy">
        <p className="eyebrow">{strings.continueHeading}</p>
        <h2 id="continue-heading">{title}</h2>
        <p className="hint">
          {book.page_count > 0 ? strings.pageCount(book.page_count) : null}
          {percent !== null ? ` · ${strings.progressPercent(percent)}` : null}
        </p>
        {percent !== null ? <ProgressBar percent={percent} label={title} /> : null}
        {book.reading?.stale ? <p className="hint">{strings.resumeStale}</p> : null}
        <Link className="btn btn-primary continue-action" href={`/documents/${book.document_id}`}>
          {strings.continueResume}
          <span className="visually-hidden"> — {title}</span>
        </Link>
      </div>
    </section>
  );
}

function BookCard({
  book,
  onRename,
  onDelete,
}: {
  book: DocumentSummary;
  onRename: (trigger: HTMLElement) => void;
  onDelete: (trigger: HTMLElement) => void;
}) {
  const ready = isReady(book);
  const percent = percentRead(book);
  const finished = isFinished(book);
  const title = bookTitle(book);

  return (
    <li className="book-card card">
      <BookCover documentId={book.document_id} ready={ready} />

      <div className="book-card-body">
        <h3 className="book-card-title">{title}</h3>

        <p className="book-card-meta">
          {ready ? (
            <>
              {book.page_count > 0 ? (
                <span className="latin">{strings.pageCount(book.page_count)}</span>
              ) : null}
              {finished ? (
                <span className="pill pill-ok">{strings.finishedReading}</span>
              ) : percent !== null ? (
                <span className="pill pill-quiet">{strings.progressPercent(percent)}</span>
              ) : (
                <span className="pill pill-quiet">{strings.notStarted}</span>
              )}
            </>
          ) : (
            /* Not a percentage: the API reports no real progress for
               preparation, and inventing one is a lie that runs at a
               believable speed. */
            <span className="pill pill-warn">{strings.stateRunning}</span>
          )}
        </p>

        {ready && percent !== null && !finished ? (
          <ProgressBar percent={percent} label={title} />
        ) : null}

        <div className="book-card-actions">
          {ready ? (
            <Link className="btn btn-primary btn-sm" href={`/documents/${book.document_id}`}>
              {strings.continueOrOpen(book.reading !== null)}
              {/* The name is inside the link so a screen reader listing links
                  hears which book each one opens, not five identical ones. */}
              <span className="visually-hidden"> — {title}</span>
            </Link>
          ) : null}
          <button
            className="btn btn-quiet btn-sm"
            type="button"
            onClick={(event) => onRename(event.currentTarget)}
          >
            {strings.renameBook}
            <span className="visually-hidden"> — {title}</span>
          </button>
          <button
            className="btn btn-quiet btn-sm btn-danger"
            type="button"
            onClick={(event) => onDelete(event.currentTarget)}
          >
            {strings.deleteBook}
            <span className="visually-hidden"> — {title}</span>
          </button>
        </div>
      </div>
    </li>
  );
}

/**
 * How far through, for eyes and for screen readers.
 *
 * A real `progressbar` role with the value on it, so it is announced as a
 * measurement rather than as a decorative bar. The visible percentage is in
 * the card's text already, so this one is labelled and not duplicated aloud.
 */
function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`${label}: ${strings.progressPercent(percent)}`}
    >
      <span className="progress-fill" style={{ inlineSize: `${percent}%` }} />
    </div>
  );
}

function SearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 16 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
