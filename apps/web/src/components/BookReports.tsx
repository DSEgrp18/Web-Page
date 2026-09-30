"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useReader } from "@/components/ReaderProvider";
import type { ReportView } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Quoted, Typed } from "@/components/BookText";

/** The problems readers reported on the owner's book, newest first, unsigned. */
export function BookReports({ documentId }: { documentId: string }) {
  const strings = useStrings();
  const { api } = useReader();
  const { setFailure, notice } = useFailure();
  const [title, setTitle] = useState("");
  const [reports, setReports] = useState<ReportView[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getDocument(documentId).then(
      (book) => {
        if (!cancelled) setTitle(book.title?.trim() || book.filename);
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

  return (
    <div className="account-page">
      <p>
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
              {report.sentence ? (
                <p>
                  <Quoted format={strings.reportsSentence} text={report.sentence} />
                </p>
              ) : null}
              {report.question_id ? <p className="hint">{strings.reportsQuestion}</p> : null}
              <p>
                <Typed text={report.message} />
              </p>
              {report.segment_id && report.sentence ? (
                <Link
                  href={`/library/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(report.segment_id)}`}
                >
                  {strings.hearSource}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
