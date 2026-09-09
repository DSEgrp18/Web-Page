"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
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
  const fileInputId = useId();
  const uploadHelpId = useId();
  const formRef = useRef<HTMLFormElement>(null);

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
      } catch (cause) {
        fail(cause);
      } finally {
        setBusy(false);
      }
    },
    [api, refresh, say, alert, fail],
  );

  const remove = useCallback(
    async (book: DocumentSummary) => {
      // Deletion removes derived text, audio and caches on the server. Saying
      // so before it happens is the only chance the reader gets to stop.
      if (!window.confirm(strings.deleteConfirm)) return;
      try {
        await api.deleteDocument(book.document_id);
        say(strings.deleted);
        await refresh();
      } catch (cause) {
        fail(cause);
      }
    },
    [api, refresh, say, fail],
  );

  return (
    <>
      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      <section aria-labelledby="upload-heading" className="panel">
        <h2 id="upload-heading">{strings.uploadHeading}</h2>
        <form ref={formRef} onSubmit={upload}>
          <div className="field">
            <label htmlFor={fileInputId}>{strings.uploadLabel}</label>
            <input
              id={fileInputId}
              name="file"
              type="file"
              accept="application/pdf,.pdf"
              aria-describedby={uploadHelpId}
              disabled={busy}
            />
            <p className="hint" id={uploadHelpId}>
              {strings.uploadHelp}
            </p>
          </div>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? strings.uploadInProgress : strings.uploadSubmit}
          </button>
        </form>
      </section>

      <section aria-labelledby="library-heading">
        <h2 id="library-heading">{strings.libraryHeading}</h2>
        {documents === null ? null : documents.length === 0 ? (
          <p>{strings.libraryEmpty}</p>
        ) : (
          <ul className="stack">
            {documents.map((book) => (
              <DocumentRow key={book.document_id} book={book} onDelete={remove} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function DocumentRow({
  book,
  onDelete,
}: {
  book: DocumentSummary;
  onDelete: (book: DocumentSummary) => void;
}) {
  const ready = book.version !== null;
  const state = ready ? "succeeded" : "running";
  return (
    <li>
      <h3>{book.filename}</h3>
      <p className="hint">
        {jobStateMessage(state)}
        {ready ? ` · ${strings.pageCount(book.page_count)}` : null}
      </p>
      <p className="row">
        {ready ? (
          <Link className="button" href={`/documents/${book.document_id}`}>
            {strings.open}
            {/* The name is inside the link so a screen reader listing links
                hears which book each one opens, not five identical "open"s. */}
            <span className="visually-hidden"> — {book.filename}</span>
          </Link>
        ) : null}
        <button type="button" onClick={() => onDelete(book)}>
          {strings.deleteBook}
          <span className="visually-hidden"> — {book.filename}</span>
        </button>
      </p>
    </li>
  );
}
