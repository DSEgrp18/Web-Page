"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { DocumentDetail, StudyAnswer } from "@/lib/types";

/**
 * Study mode deliberately displays the service's extract rather than pretending
 * it is a generated explanation. Every successful result keeps the linked
 * passage in sight, so a reader can immediately check the source in context.
 */
export function Study({ documentId }: { documentId: string }) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const [book, setBook] = useState<DocumentDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<StudyAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const fail = useCallback(
    (cause: unknown) => {
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.errorServer;
      setError(message);
      alert(message);
    },
    [alert],
  );

  useEffect(() => {
    let cancelled = false;
    void api
      .getDocument(documentId)
      .then((detail) => {
        if (!cancelled) setBook(detail);
      })
      .catch((cause: unknown) => {
        if (!cancelled) fail(cause);
      });
    return () => {
      cancelled = true;
    };
  }, [api, documentId, fail]);

  const ask = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = question.trim();
      if (!trimmed) {
        setError(strings.questionRequired);
        alert(strings.questionRequired);
        return;
      }
      setAsking(true);
      setError(null);
      setResult(null);
      try {
        const answer = await api.askQuestion(documentId, trimmed);
        setResult(answer);
        say(answer.abstained ? strings.studyAbstainedHeading : strings.answerFound);
      } catch (cause) {
        fail(cause);
      } finally {
        setAsking(false);
      }
    },
    [alert, api, documentId, fail, question, say],
  );

  if (error && !book) {
    return <ErrorNotice message={error} onRetry={() => window.location.reload()} />;
  }
  if (!book) return <p>{strings.pageLoading}</p>;

  return (
    <div className="study-page">
      <p className="study-topline">
        <Link href={`/documents/${encodeURIComponent(documentId)}`}>{strings.backToReader}</Link>
      </p>

      <header className="study-heading">
        <h1>{strings.studyHeading}</h1>
        <p>{book.filename}</p>
        <p className="hint">{strings.studyIntro}</p>
      </header>

      {error ? <ErrorNotice message={error} onDismiss={() => setError(null)} /> : null}

      <form className="study-form panel" onSubmit={(event) => void ask(event)}>
        <label htmlFor="study-question">{strings.questionLabel}</label>
        <textarea
          id="study-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={strings.questionPlaceholder}
          maxLength={500}
          rows={4}
          disabled={asking}
        />
        <p className="hint">{strings.studyHonesty}</p>
        <button className="primary" type="submit" disabled={asking}>
          {asking ? strings.answering : strings.askQuestion}
        </button>
      </form>

      {result?.abstained ? (
        <section className="notice study-abstained" aria-labelledby="study-abstained-heading">
          <h2 id="study-abstained-heading">{strings.studyAbstainedHeading}</h2>
          <p>{strings.studyAbstainedBody}</p>
        </section>
      ) : null}

      {result?.answer ? (
        <section className="study-result" aria-labelledby="study-answer-heading">
          <h2 id="study-answer-heading">{strings.answerHeading}</h2>
          <blockquote>{result.answer}</blockquote>
          {result.citations.length > 0 ? (
            <section aria-labelledby="study-sources-heading">
              <h3 id="study-sources-heading">{strings.sourcesHeading}</h3>
              <ol className="study-citations">
                {result.citations.map((citation) => {
                  const page = citation.page_label ?? String(citation.page_index + 1);
                  const segmentId = citation.segment_ids[0];
                  const href = segmentId
                    ? `/documents/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(segmentId)}`
                    : `/documents/${encodeURIComponent(documentId)}`;
                  return (
                    <li key={citation.passage_id} className="study-citation">
                      <p className="study-citation-place">
                        {strings.citationPage(page)}
                        {citation.section
                          ? ` · ${strings.citationSection(citation.section)}`
                          : null}
                      </p>
                      <p>{citation.quote}</p>
                      <Link className="button" href={href}>
                        {strings.openCitation}
                      </Link>
                    </li>
                  );
                })}
              </ol>
            </section>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
