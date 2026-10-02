"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useReader } from "@/components/ReaderProvider";
import { bookTitle } from "@/lib/books";
import type { ReportKind } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Quoted } from "@/components/BookText";

const KINDS: ReportKind[] = ["pronunciation", "extraction", "question", "accessibility", "other"];

export interface ReportTarget {
  document?: string;
  segment?: string;
  quiz?: string;
  question?: string;
  kind?: string;
}

/**
 * Report a problem with a sentence, a question, or the site. What it is about
 * comes from the link that opened it; the reader chooses the kind and says
 * what is wrong. It says plainly who will read it.
 */
export function ReportForm({ target }: { target: ReportTarget }) {
  const strings = useStrings();
  const { api } = useReader();
  const { setFailure, notice } = useFailure();
  const initial =
    KINDS.find((k) => k === target.kind) ?? (target.segment ? "pronunciation" : "other");
  const [kind, setKind] = useState<ReportKind>(initial);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [bookName, setBookName] = useState<string | null>(null);
  const [sentence, setSentence] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const messageId = useId();
  const name = useId();

  useEffect(() => {
    if (!target.document) return;
    let cancelled = false;
    void (async () => {
      try {
        const book = await api.getDocument(target.document!);
        if (!cancelled) setBookName(bookTitle(book));
      } catch {
        /* The form still works; the subject line stays empty. */
      }
      if (target.segment) {
        try {
          const segment = await api.getSegment(target.document!, target.segment);
          if (!cancelled) setSentence(segment.display_text);
        } catch {
          /* Segment may have moved after a reprocessing. */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, target.document, target.segment]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!message.trim()) return setFailure(strings.reportMessageRequired);
    setBusy(true);
    try {
      await api.report({
        kind,
        message: message.trim(),
        document_id: target.document,
        segment_id: target.segment,
        quiz_id: target.quiz,
        question_id: target.question,
      });
      setFailure(null);
      setSent(true);
      heading.current?.focus();
    } catch (error) {
      setFailure(explain(error, {}, strings));
    } finally {
      setBusy(false);
    }
  }

  const back = target.document
    ? `/library/${encodeURIComponent(target.document)}${
        target.segment ? `?segment=${encodeURIComponent(target.segment)}` : ""
      }`
    : "/library";
  return (
    <div className="account-page">
      <h1 ref={heading} tabIndex={-1}>
        {sent ? strings.reportSent : strings.reportHeading}
      </h1>
      {sent ? (
        <p>
          <Link href={back}>{target.document ? strings.backToReader : strings.backToLibrary}</Link>
        </p>
      ) : (
        <>
          <p className="hint">{target.document ? strings.reportWhoBook : strings.reportWhoSite}</p>
          {bookName ? (
            <p>
              <strong>{strings.reportAboutBook}</strong> {bookName}
            </p>
          ) : null}
          {sentence ? (
            <p lang="si">
              <Quoted format={strings.reportAboutSentence} text={sentence} />
            </p>
          ) : null}
          {target.question ? <p className="hint">{strings.reportsQuestion}</p> : null}
          {notice}
          <form className="account-fields" onSubmit={submit} noValidate>
            <fieldset className="decision">
              <legend>{strings.reportKindLegend}</legend>
              {KINDS.map((option) => (
                <label key={option} className="check-row">
                  <input
                    type="radio"
                    name={name}
                    checked={kind === option}
                    onChange={() => setKind(option)}
                  />
                  {strings.reportKinds[option]}
                </label>
              ))}
            </fieldset>
            <div className="field">
              <label htmlFor={messageId}>{strings.reportMessageLabel}</label>
              <textarea
                id={messageId}
                rows={5}
                maxLength={1000}
                required
                value={message}
                onChange={(event) => setMessage(event.target.value)}
              />
            </div>
            <button className="btn btn-primary" type="submit" aria-busy={busy}>
              {strings.reportSend}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
