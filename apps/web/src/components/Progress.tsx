"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type { BookProgress, ChapterProgress, ProgressReport } from "@/lib/types";

/**
 * What a reader has heard, how their answers went, and what to revise next.
 *
 * Text first, for a screen reader: one summary sentence, then one captioned
 * table per book, then links. Nothing here is carried only by a chart or a
 * colour.
 */
export function Progress() {
  const { api } = useReader();
  const { setFailure, notice } = useFailure();
  const [report, setReport] = useState<ProgressReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.myProgress().then(
      (found) => {
        if (!cancelled) setReport(found);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, setFailure]);

  return (
    <div className="account-page">
      <h1>{strings.progressHeading}</h1>
      {notice}
      {report === null ? (
        <p className="hint" aria-busy="true">
          {strings.pageLoading}
        </p>
      ) : report.books.length === 0 ? (
        <p>{strings.progressNoBooks}</p>
      ) : (
        <>
          <p>
            {strings.progressSummary(report.chapters_complete, report.chapter_count, report.due)}
          </p>

          <section className="account-section card" aria-labelledby="revise-heading">
            <h2 id="revise-heading">{strings.reviseHeading}</h2>
            {report.revise.length === 0 ? (
              <p>{strings.reviseNothing}</p>
            ) : (
              <ul>
                {report.revise.map((item) => (
                  <li key={item.quiz_id}>
                    <Link
                      href={`/library/${encodeURIComponent(item.document_id)}/practice?review=${encodeURIComponent(item.quiz_id)}`}
                    >
                      {strings.reviseLink(item.title, item.due)}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {report.books.map((book) => (
            <section key={book.document_id} className="account-section card">
              <BookTable book={book} />
            </section>
          ))}
        </>
      )}
    </div>
  );
}

function chapterName(chapter: ChapterProgress, only: boolean): string {
  if (chapter.title) return chapter.title;
  return only ? strings.progressWholeBook : strings.progressOpening;
}

/** One book, chapter by chapter. Shared with the teacher's view of a student. */
export function BookTable({ book }: { book: BookProgress }) {
  const only = book.chapters.length === 1;
  return (
    <table className="member-table">
      <caption>{strings.progressCaption(book.title)}</caption>
      <thead>
        <tr>
          <th scope="col">{strings.progressChapter}</th>
          <th scope="col">{strings.progressHeard}</th>
          <th scope="col">{strings.progressAnswered}</th>
          <th scope="col">{strings.progressDue}</th>
        </tr>
      </thead>
      <tbody>
        {book.chapters.map((chapter) => (
          <tr key={`${chapter.first_page}-${chapter.title ?? ""}`}>
            <th scope="row">{chapterName(chapter, only)}</th>
            <td>{strings.progressHeardCell(chapter.heard, chapter.sentences)}</td>
            <td>{strings.progressAnsweredCell(chapter.correct, chapter.answered)}</td>
            <td>{chapter.due}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
