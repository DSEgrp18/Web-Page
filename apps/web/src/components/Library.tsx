"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { jobStateMessage, messageFor, strings } from "@/lib/strings";
import type { DocumentSummary } from "@/lib/types";

/** How often to ask whether a book has finished preparing. */
const POLL_MS = 1500;

export function Library() {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();

  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<DocumentSummary | null>(null);
  const fileInputId = useId();
  const uploadHelpId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);

  /** Which books were still being prepared last time we looked. */
  const pendingRef = useRef(new Set<string>());

  const apply = useCallback(
    (listed: DocumentSummary[]) => {
      setDocuments(listed);
      setError(null);

      // Announce only the transition, not every poll. CLAUDE.md is explicit
      // that routine progress must not be narrated on every update; a book
      // becoming ready is news, "still working" every second and a half is not.
      const stillPending = new Set<string>();
      for (const book of listed) {
        if (book.version === null) stillPending.add(book.document_id);
        else if (pendingRef.current.has(book.document_id)) say(strings.prepared);
      }
      pendingRef.current = stillPending;
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

  // Poll only while something is actually being prepared, and stop as soon as
  // nothing is. An idle library makes no requests: this runs on a student's
  // phone, on their data.
  const anyPending = (documents ?? []).some((book) => book.version === null);
  useEffect(() => {
    if (!anyPending) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [anyPending, refresh]);

  const upload = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const input = event.currentTarget.elements.namedItem("file") as HTMLInputElement | null;
      const file = input?.files?.[0];
      if (!file) {
        setError(strings.uploadNoFile);
        alert(strings.uploadNoFile);
        return;
      }
      setBusy(true);
      setError(null);
      say(strings.uploadInProgress);
      try {
        const created = await api.upload(file);
        pendingRef.current.add(created.document_id);
        say(strings.preparing);
        formRef.current?.reset();
        await refresh();
        setShowUpload(false);
      } catch (cause) {
        fail(cause);
      } finally {
        setBusy(false);
      }
    },
    [api, refresh, say, alert, fail],
  );

  const requestDelete = useCallback((book: DocumentSummary, trigger: HTMLElement) => {
    deleteTriggerRef.current = trigger;
    setPendingDelete(book);
  }, []);

  const cancelDelete = useCallback(() => {
    setPendingDelete(null);
  }, []);

  const confirmDelete = useCallback(async () => {
    const book = pendingDelete;
    setPendingDelete(null);
    if (!book) return;
    try {
      await api.deleteDocument(book.document_id);
      say(strings.deleted);
      await refresh();
    } catch (cause) {
      fail(cause);
    }
  }, [api, pendingDelete, refresh, say, fail]);

  const primaryBook = documents?.find((book) => book.version !== null) ?? documents?.[0] ?? null;
  const shownBooks = (documents ?? []).filter((book) =>
    book.filename.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );

  return (
    <div className="library-page">
      <header className="library-header">
        <div>
          <p className="breadcrumb">
            {strings.appName} / {strings.libraryHeading}
          </p>
          <h1>{strings.libraryHeading}</h1>
          <p className="library-subtitle">{strings.appTagline}</p>
        </div>
        {!showUpload && documents && documents.length > 0 ? (
          <button
            className="primary library-add-button"
            type="button"
            onClick={() => setShowUpload(true)}
          >
            + {strings.addBook}
          </button>
        ) : null}
      </header>

      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      {documents === null ? (
        <p className="hint" aria-busy="true">
          {strings.pageLoading}
        </p>
      ) : showUpload ? (
        <UploadBook
          busy={busy}
          fileInputId={fileInputId}
          helpId={uploadHelpId}
          formRef={formRef}
          onCancel={() => setShowUpload(false)}
          onSubmit={upload}
        />
      ) : documents.length === 0 ? (
        <EmptyLibrary onStart={() => setShowUpload(true)} />
      ) : (
        <>
          {primaryBook ? <CurrentBook book={primaryBook} /> : null}
          <section aria-labelledby="library-heading" className="library-books">
            <div className="library-books-heading">
              <h2 id="library-heading">{strings.browseBooks}</h2>
              <label className="library-search" htmlFor="library-search">
                <span className="visually-hidden">{strings.searchLibrary}</span>
                <input
                  id="library-search"
                  type="search"
                  value={query}
                  placeholder={strings.searchLibraryPlaceholder}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
            </div>
            {shownBooks.length === 0 ? (
              <p className="hint">{strings.libraryEmpty}</p>
            ) : (
              <ul className="book-grid">
                {shownBooks.map((book) => (
                  <DocumentRow key={book.document_id} book={book} onDelete={requestDelete} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={strings.deleteConfirmTitle}
        body={pendingDelete ? strings.deleteConfirmBody(pendingDelete.filename) : null}
        cancelLabel={strings.deleteConfirmCancel}
        confirmLabel={strings.deleteConfirmAction}
        onCancel={cancelDelete}
        onConfirm={() => void confirmDelete()}
        returnFocusRef={deleteTriggerRef}
      />
    </div>
  );
}

function EmptyLibrary({ onStart }: { onStart: () => void }) {
  return (
    <section className="library-empty" aria-labelledby="empty-library-heading">
      <div className="book-cover book-cover-empty" aria-hidden="true">
        <span />
      </div>
      <h2 id="empty-library-heading">{strings.libraryEmpty}</h2>
      <p>{strings.uploadIntro}</p>
      <button className="primary" type="button" onClick={onStart}>
        + {strings.addBook}
      </button>
    </section>
  );
}

function UploadBook({
  busy,
  fileInputId,
  helpId,
  formRef,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  fileInputId: string;
  helpId: string;
  formRef: React.RefObject<HTMLFormElement | null>;
  onCancel: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  const [filename, setFilename] = useState("");

  return (
    <section className="upload-state" aria-labelledby="upload-heading">
      <h2 id="upload-heading">{strings.uploadHeading}</h2>
      <p>{strings.uploadIntro}</p>
      <form ref={formRef} className="upload-sheet" onSubmit={onSubmit}>
        <div className="upload-dropzone">
          <span className="upload-arrow" aria-hidden="true">
            ↑
          </span>
          <label htmlFor={fileInputId}>{strings.uploadLabel}</label>
          <p id={helpId}>{strings.uploadDropHelp}</p>
          <input
            id={fileInputId}
            name="file"
            type="file"
            accept="application/pdf,.pdf"
            aria-describedby={helpId}
            disabled={busy}
            onChange={(event) => setFilename(event.target.files?.[0]?.name ?? "")}
          />
        </div>
        {filename ? (
          <p className="selected-file">
            <strong>{strings.uploadSelected}:</strong> {filename}
          </p>
        ) : null}
        <div className="row upload-actions">
          <button className="primary" type="submit" disabled={busy}>
            {busy ? strings.uploadInProgress : strings.uploadSubmit}
          </button>
          <button type="button" onClick={onCancel} disabled={busy}>
            {strings.deleteConfirmCancel}
          </button>
        </div>
      </form>
    </section>
  );
}

function CurrentBook({ book }: { book: DocumentSummary }) {
  const ready = book.version !== null;
  return (
    <section className="current-book" aria-labelledby="current-book-heading">
      <div className="current-book-copy">
        <p>{strings.currentReading}</p>
        <h2 id="current-book-heading">{book.filename}</h2>
        <p className="current-book-meta">
          {ready ? strings.pageCount(book.page_count) : strings.preparingBook}
        </p>
        {ready ? (
          <Link className="button current-book-action" href={`/documents/${book.document_id}`}>
            ▶ {strings.beginReading}
          </Link>
        ) : null}
      </div>
      <div className="book-cover current-book-cover" aria-hidden="true">
        <span />
      </div>
    </section>
  );
}

function DocumentRow({
  book,
  onDelete,
}: {
  book: DocumentSummary;
  onDelete: (book: DocumentSummary, trigger: HTMLElement) => void;
}) {
  const ready = book.version !== null;
  const state = ready ? "succeeded" : "running";
  return (
    <li className="book-card">
      <div className="book-cover" aria-hidden="true">
        <span />
      </div>
      <div className="book-card-body">
        <h3>{book.filename}</h3>
        <p className="book-status">
          {jobStateMessage(state)}
          {ready ? ` · ${strings.pageCount(book.page_count)}` : null}
        </p>
        <div className="row book-actions">
          {ready ? (
            <Link className="button primary" href={`/documents/${book.document_id}`}>
              {strings.open}
              {/* The name is inside the link so a screen reader listing links
                hears which book each one opens, not five identical "open"s. */}
              <span className="visually-hidden"> — {book.filename}</span>
            </Link>
          ) : null}
          <button type="button" onClick={(event) => onDelete(book, event.currentTarget)}>
            {strings.deleteBook}
            <span className="visually-hidden"> — {book.filename}</span>
          </button>
        </div>
      </div>
    </li>
  );
}
