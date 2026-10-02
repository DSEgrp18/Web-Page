"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { bookTitle } from "@/lib/books";
import type { ReportView } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Quoted, Typed } from "@/components/BookText";

/** The problems readers reported on the owner's book, newest first, unsigned. */
export function BookReports({ documentId }: { documentId: string }) {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [title, setTitle] = useState("");
  const [reports, setReports] = useState<ReportView[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getDocument(documentId).then(
      (book) => {
        if (!cancelled) setTitle(bookTitle(book));
      },
      () => {},
    );
    api.listReports(documentId).then(
      (found) => {
        if (!cancelled) setReports(found);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}, strings));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, documentId, setFailure, strings]);

  async function markHandled(reportId: string) {
    try {
      await api.markReportHandled(documentId, reportId);
      setReports(
        (rows) =>
          rows?.map((row) =>
            row.report_id === reportId ? { ...row, handled_at: new Date().toISOString() } : row,
          ) ?? null,
      );
      say(strings.reportMarkedHandled);
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  return (
    <div className="account-page">
      <p>
        <Link href={`/library/${encodeURIComponent(documentId)}`}>{strings.backToReader}</Link>
        {" · "}
        <Link href={`/library/${encodeURIComponent(documentId)}/share`}>{strings.shareBook}</Link>
      </p>
      <h1>{strings.reportsHeading(title)}</h1>
      {notice}
      {reports === null ? null : reports.length === 0 ? (
        <p>{strings.reportsNone}</p>
      ) : (
        <ul className="class-list">
          {reports.map((report) => (
            <li key={report.report_id} className="class-item">
              <h2>{strings.reportKinds[report.kind] ?? report.kind}</h2>
              {report.handled_at ? <p className="hint">{strings.reportHandled}</p> : null}
              {report.sentence ? (
                <p>
                  <Quoted format={strings.reportsSentence} text={report.sentence} />
                </p>
              ) : null}
              {report.question_id ? <p className="hint">{strings.reportsQuestion}</p> : null}
              <p>
                <Typed text={report.message} />
              </p>
              <div className="notice-actions">
                {report.segment_id && report.sentence ? (
                  <Link
                    className="btn btn-quiet btn-sm"
                    href={`/library/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(report.segment_id)}`}
                  >
                    {strings.hearSource}
                  </Link>
                ) : null}
                {!report.handled_at ? (
                  <button
                    className="btn btn-sm"
                    type="button"
                    onClick={() => void markHandled(report.report_id)}
                  >
                    {strings.markReportHandled}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
