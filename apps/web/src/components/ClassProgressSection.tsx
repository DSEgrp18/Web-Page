"use client";

import { useEffect, useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { BookTable } from "@/components/Progress";
import { useReader } from "@/components/ReaderProvider";
import type { ClassProgress } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";

/**
 * The teacher's view of a class's progress: only students who chose to share,
 * only on the books published to this class. A list of students, each opening
 * their own table, because a grid of students by chapters cannot be followed
 * by ear.
 */
export function ClassProgressSection({ classId }: { classId: string }) {
  const strings = useStrings();
  const { api } = useReader();
  const { setFailure, notice } = useFailure();
  const [report, setReport] = useState<ClassProgress | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.classProgress(classId).then(
      (found) => {
        if (!cancelled) setReport(found);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}, strings));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, classId, setFailure, strings]);

  async function download() {
    try {
      const sheet = await api.classProgressSheet(classId);
      const url = URL.createObjectURL(sheet);
      const link = document.createElement("a");
      link.href = url;
      link.download = "class-progress.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  return (
    <section className="account-section card" aria-labelledby="class-progress-heading">
      <h2 id="class-progress-heading">{strings.classProgressHeading}</h2>
      <p className="hint">{strings.classProgressHow}</p>
      {notice}
      {report === null ? null : (
        <>
          {report.not_sharing > 0 ? <p>{strings.classNotSharing(report.not_sharing)}</p> : null}
          {report.students.length === 0 ? (
            <p>{strings.classProgressNobody}</p>
          ) : (
            <>
              <ul className="class-list">
                {report.students.map((student, position) => (
                  <li key={`${position}-${student.display_name}`} className="class-item">
                    <details>
                      <summary>{student.display_name}</summary>
                      {student.books.length === 0 ? (
                        <p>{strings.classProgressNoBooks}</p>
                      ) : (
                        student.books.map((book) => (
                          <BookTable key={book.document_id} book={book} />
                        ))
                      )}
                    </details>
                  </li>
                ))}
              </ul>
              <div className="notice-actions">
                <button className="btn" type="button" onClick={() => void download()}>
                  {strings.classProgressDownload}
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
