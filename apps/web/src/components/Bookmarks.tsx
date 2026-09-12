"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { Bookmark, DocumentSummary } from "@/lib/types";

interface BookmarkGroup {
  document: DocumentSummary;
  bookmarks: Bookmark[];
}

/**
 * A reader's saved places across their own library.
 *
 * The API intentionally lists bookmarks one document at a time, so this
 * client screen joins those private lists with the document names it already
 * owns. It does not invent a server-wide bookmark feed or expose another
 * reader's book title.
 */
export function Bookmarks() {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const [groups, setGroups] = useState<BookmarkGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const documents = await api.listDocuments();
      const loaded = await Promise.all(
        documents.map(async (document) => ({
          document,
          bookmarks: await api.listBookmarks(document.document_id),
        })),
      );
      setGroups(loaded.filter((group) => group.bookmarks.length > 0));
    } catch (cause) {
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
      setError(message);
      alert(message);
    } finally {
      setLoading(false);
    }
  }, [alert, api]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const documents = await api.listDocuments();
        const loaded = await Promise.all(
          documents.map(async (document) => ({
            document,
            bookmarks: await api.listBookmarks(document.document_id),
          })),
        );
        if (!cancelled) setGroups(loaded.filter((group) => group.bookmarks.length > 0));
      } catch (cause) {
        if (cancelled) return;
        const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
        setError(message);
        alert(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [alert, api]);

  const remove = useCallback(
    async (documentId: string, bookmark: Bookmark) => {
      setRemoving(bookmark.bookmark_id);
      try {
        await api.deleteBookmark(documentId, bookmark.bookmark_id);
        setGroups((current) =>
          current
            .map((group) =>
              group.document.document_id === documentId
                ? {
                    ...group,
                    bookmarks: group.bookmarks.filter(
                      (item) => item.bookmark_id !== bookmark.bookmark_id,
                    ),
                  }
                : group,
            )
            .filter((group) => group.bookmarks.length > 0),
        );
        say(strings.bookmarkRemoved);
      } catch (cause) {
        const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
        setError(message);
        alert(message);
      } finally {
        setRemoving(null);
      }
    },
    [alert, api, say],
  );

  const count = groups.reduce((total, group) => total + group.bookmarks.length, 0);

  return (
    <div className="bookmarks-page">
      <header className="bookmarks-heading">
        <p className="eyebrow">{strings.appName}</p>
        <h1>{strings.bookmarksHeading}</h1>
        <p>{strings.bookmarksIntro}</p>
      </header>

      {error ? (
        <ErrorNotice message={error} onRetry={() => void load()} onDismiss={() => setError(null)} />
      ) : null}

      {loading ? (
        <p>{strings.bookmarksLoading}</p>
      ) : count === 0 ? (
        <section className="bookmarks-empty panel" aria-labelledby="bookmarks-empty-heading">
          <h2 id="bookmarks-empty-heading">{strings.bookmarksEmptyTitle}</h2>
          <p>{strings.bookmarksEmptyBody}</p>
          <Link className="button primary" href="/">
            {strings.libraryHeading}
          </Link>
        </section>
      ) : (
        <div className="bookmark-groups">
          {groups.map((group) => (
            <section
              key={group.document.document_id}
              className="bookmark-group"
              aria-labelledby={`book-${group.document.document_id}`}
            >
              <h2 id={`book-${group.document.document_id}`}>{group.document.filename}</h2>
              <ul className="bookmark-list">
                {group.bookmarks.map((bookmark) => {
                  const page =
                    bookmark.page_label ??
                    (bookmark.page_index === null
                      ? strings.bookmarkNoPage
                      : String(bookmark.page_index + 1));
                  const pageName = `${strings.pageWord} ${page}`;
                  const canOpen = bookmark.segment_found && bookmark.page_index !== null;
                  return (
                    <li key={bookmark.bookmark_id} className="bookmark-card">
                      <div>
                        <p className="bookmark-page">{pageName}</p>
                        {bookmark.display_text ? (
                          <p className="bookmark-text">{bookmark.display_text}</p>
                        ) : null}
                        {bookmark.note ? <p className="bookmark-note">{bookmark.note}</p> : null}
                        {bookmark.stale ? (
                          <p className="bookmark-warning">{strings.bookmarkStale}</p>
                        ) : null}
                        {!bookmark.segment_found ? (
                          <p className="bookmark-warning">{strings.bookmarkMissing}</p>
                        ) : null}
                      </div>
                      <div className="row bookmark-actions">
                        {canOpen ? (
                          <Link
                            className="button"
                            href={`/documents/${encodeURIComponent(bookmark.document_id)}?segment=${encodeURIComponent(bookmark.segment_id)}`}
                          >
                            {strings.bookmarkOpen}
                          </Link>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => void remove(group.document.document_id, bookmark)}
                          disabled={removing === bookmark.bookmark_id}
                          aria-label={strings.bookmarkRemoveNamed(group.document.filename, page)}
                        >
                          {strings.bookmarkRemove}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
