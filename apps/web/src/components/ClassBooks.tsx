"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BookCover } from "@/components/BookCover";
import { useReader } from "@/components/ReaderProvider";
import { bookTitle } from "@/lib/books";
import type { ClassBook } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Typed } from "@/components/BookText";

/**
 * "From your classes": the books a reader's teachers have shared with them.
 *
 * A section of its own, after the reader's own shelf, rather than mixed into
 * it: these books are not theirs to rename or delete, and a shelf where some
 * cards have those buttons and some do not is a shelf that has to be learned.
 * Absent entirely when there are none, so a reader in no class hears nothing
 * about classes on their own library.
 *
 * Each card opens its book the way the reader's own cards do — one "open" or
 * "continue" button naming the book — rather than from its title, so there is
 * one way to open a book on this page, not two.
 */
export function ClassBooks() {
  const strings = useStrings();
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
      <ul className="book-grid">
        {books.map(({ class_id, class_name, book }) => {
          const title = bookTitle(book);
          const id = encodeURIComponent(book.document_id);
          return (
            <li key={`${class_id}:${book.document_id}`} className="book-card card">
              <BookCover documentId={book.document_id} ready title={title} />
              <div className="book-card-body">
                <h3 className="book-card-title">
                  <Typed text={title} />
                </h3>
                <p className="hint">{strings.classBookFrom(class_name)}</p>
                <div className="book-card-actions">
                  <Link className="btn btn-primary btn-sm" href={`/library/${id}`}>
                    {strings.continueOrOpen(book.reading !== null)}
                    <span className="visually-hidden">
                      {" — "}
                      <Typed text={title} />
                    </span>
                  </Link>
                  <Link className="btn btn-quiet btn-sm" href={`/library/${id}/practice`}>
                    {strings.practiceLink}
                    <span className="visually-hidden">
                      {" — "}
                      <Typed text={title} />
                    </span>
                  </Link>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
