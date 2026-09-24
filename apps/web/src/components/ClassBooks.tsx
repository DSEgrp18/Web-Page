"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useReader } from "@/components/ReaderProvider";
import { bookTitle } from "@/lib/books";
import { strings } from "@/lib/strings";
import type { ClassBook } from "@/lib/types";

/**
 * "From your classes": the books a reader's teachers have shared with them.
 *
 * A section of its own, after the reader's own shelf, rather than mixed into
 * it: these books are not theirs to rename or delete, and a shelf where some
 * cards have those buttons and some do not is a shelf that has to be learned.
 * Absent entirely when there are none, so a reader in no class hears nothing
 * about classes on their own library.
 */
export function ClassBooks() {
  const { api } = useReader();
  const [books, setBooks] = useState<ClassBook[]>([]);

  useEffect(() => {
    let cancelled = false;
    api.classBooks().then(
      (found) => {
        if (!cancelled) setBooks(found);
      },
      () => {
        // The reader's own shelf reports failures; this section just stays away.
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api]);

  if (books.length === 0) return null;

  return (
    <section className="shelf" aria-labelledby="class-books-heading">
      <h2 id="class-books-heading">{strings.fromYourClasses}</h2>
      <ul className="class-list">
        {books.map(({ class_id, class_name, book }) => (
          <li key={`${class_id}:${book.document_id}`} className="class-item">
            <h3>
              <Link href={`/library/${encodeURIComponent(book.document_id)}`}>
                {bookTitle(book)}
              </Link>
            </h3>
            <p className="hint">{strings.classBookFrom(class_name)}</p>
            <Link
              className="btn btn-quiet btn-sm"
              href={`/library/${encodeURIComponent(book.document_id)}/practice`}
            >
              {strings.practiceLink}
              <span className="visually-hidden"> — {bookTitle(book)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
