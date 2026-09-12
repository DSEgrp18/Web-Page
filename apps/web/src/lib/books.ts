/**
 * What the library knows about a book, derived from what the API returns.
 *
 * Pure functions, kept out of the component so they can be tested without
 * rendering anything. The interesting ones are the edges: a book with no
 * sentences, a position saved against an older version of the text, a book
 * still being prepared.
 */

import type { DocumentSummary } from "./types";

export type Shelf = "all" | "reading" | "finished" | "processing";
export type Order = "recent" | "added" | "title";

/** What to call a book: the reader's name for it, or the file they uploaded. */
export function bookTitle(book: DocumentSummary): string {
  return book.title?.trim() || book.filename;
}

/** A book is readable once preparation has produced a version. */
export function isReady(book: DocumentSummary): boolean {
  return book.version !== null;
}

/**
 * How far through, 0–100.
 *
 * Null rather than 0 when there is no position, because "not started" and
 * "0% read" look the same on a bar and mean different things in a sentence.
 *
 * A position saved against an older version of the text is deliberately still
 * counted. It is approximate — the sentence may have moved — but it is closer
 * to the truth than showing nothing, and `stale` is surfaced separately where
 * it actually matters, which is when resuming.
 */
export function percentRead(book: DocumentSummary): number | null {
  if (!book.reading || book.segment_count <= 0) return null;
  // segment_index is 0-based, so finishing the last sentence is index n-1.
  const through = (book.reading.segment_index + 1) / book.segment_count;
  return Math.max(0, Math.min(100, Math.round(through * 100)));
}

/**
 * Finished means the last sentence was reached.
 *
 * Not "100% by rounding": a 400-sentence book rounds to 100% from sentence
 * 398, and telling a reader they have finished a book they have not is worse
 * than showing 99%.
 */
export function isFinished(book: DocumentSummary): boolean {
  if (!book.reading || book.segment_count <= 0) return false;
  return book.reading.segment_index >= book.segment_count - 1;
}

export function shelfOf(book: DocumentSummary): Exclude<Shelf, "all"> | "unread" {
  if (!isReady(book)) return "processing";
  if (isFinished(book)) return "finished";
  if (book.reading) return "reading";
  return "unread";
}

export function onShelf(book: DocumentSummary, shelf: Shelf): boolean {
  return shelf === "all" || shelfOf(book) === shelf;
}

/**
 * Title search, accent- and case-insensitive as far as the platform allows.
 *
 * Matches the filename as well as the title: a reader who renamed a book last
 * month may well search for the file they uploaded.
 */
export function matchesQuery(book: DocumentSummary, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  return (
    bookTitle(book).toLocaleLowerCase().includes(needle) ||
    book.filename.toLocaleLowerCase().includes(needle)
  );
}

/** When this book was last meaningfully touched — read if ever, else added. */
function lastTouched(book: DocumentSummary): string {
  return book.reading?.updated_at ?? book.created_at;
}

export function sortBooks(books: DocumentSummary[], order: Order): DocumentSummary[] {
  const sorted = [...books];
  switch (order) {
    case "added":
      sorted.sort((a, b) => b.created_at.localeCompare(a.created_at));
      break;
    case "title":
      // `localeCompare` with no locale uses the browser's, which orders
      // Sinhala correctly where a codepoint sort would not.
      sorted.sort((a, b) => bookTitle(a).localeCompare(bookTitle(b)));
      break;
    default:
      sorted.sort((a, b) => lastTouched(b).localeCompare(lastTouched(a)));
  }
  return sorted;
}

/**
 * The book to offer first on the landing screen.
 *
 * The most recently read one that is actually readable. A book being prepared
 * is not offered, because the button would not work; a reader who has never
 * opened anything gets no card rather than an arbitrary one.
 */
export function continueReading(books: DocumentSummary[]): DocumentSummary | null {
  const started = books.filter((b) => isReady(b) && b.reading && !isFinished(b));
  if (started.length === 0) return null;
  return sortBooks(started, "recent")[0] ?? null;
}
