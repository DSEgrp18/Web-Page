"use client";

import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { PrerenderSection } from "@/components/PrerenderSection";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type {
  DocumentDetail,
  PublicationDetail,
  Review,
  RightsBasis,
  TaughtClass,
} from "@/lib/types";

const BASES: RightsBasis[] = [
  "government_textbook",
  "public_domain",
  "publisher_permission",
  "own_work",
  "other",
];

/**
 * Sharing a book with a class, in the order the API insists on: decide on
 * every flagged page, say why you may share it, choose the classes.
 *
 * Every decision is a native radio group inside a fieldset whose legend names
 * the page, so a screen reader announces "page 12, accept, radio button" and
 * nobody has to work out which page a pair of buttons belongs to. Nothing is
 * shared until the last button is pressed.
 */
export function ShareBook({ documentId }: { documentId: string }) {
  const { api, account } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [book, setBook] = useState<DocumentDetail | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [publication, setPublication] = useState<PublicationDetail | null>(null);
  const [classes, setClasses] = useState<TaughtClass[]>([]);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [basis, setBasis] = useState<RightsBasis | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const noteId = useId();
  const noteHintId = useId();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [detail, flagged, shared, mine] = await Promise.all([
          api.getDocument(documentId),
          api.getReview(documentId),
          api.getPublication(documentId),
          api.myClasses(),
        ]);
        if (cancelled) return;
        setBook(detail);
        setReview(flagged);
        setPublication(shared);
        setClasses(mine.teaching);
      } catch (error) {
        if (!cancelled) setFailure(explain(error, {}));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, documentId, setFailure]);

  if (account && account.role !== "teacher") {
    return (
      <div className="account-page">
        <h1>{strings.shareBook}</h1>
        <p>{strings.onlyTeachersShare}</p>
      </div>
    );
  }
  if (book === null || review === null) {
    return (
      <div className="account-page">
        {notice}
        <p className="hint" aria-busy="true">
          {strings.pageLoading}
        </p>
      </div>
    );
  }

  const title = book.title?.trim() || book.filename;
  const nameOf = (classId: string) =>
    classes.find((room) => room.class_id === classId)?.name ?? classId;

  async function decide(pageIndex: number, decision: "accepted" | "withheld") {
    try {
      setReview(await api.decidePage(documentId, pageIndex, decision));
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    // Said before the request, in the order the form reads, so the reader
    // hears the first thing to fix rather than the server's first refusal.
    if (review && review.undecided > 0) return setFailure(strings.errorUnreviewed);
    if (basis === null) return setFailure(strings.errorChooseBasis);
    if (basis === "other" && !note.trim()) return setFailure(strings.errorBasisNote);
    if (chosen.size === 0) return setFailure(strings.errorChooseClass);
    setBusy(true);
    try {
      setPublication(await api.publish(documentId, [...chosen], basis, note.trim() || null));
      setFailure(null);
      setChosen(new Set());
      say(strings.published);
    } catch (error) {
      setFailure(explain(error, { 409: strings.errorUnreviewed }));
    } finally {
      setBusy(false);
    }
  }

  async function stop(classId: string) {
    try {
      await api.unpublish(documentId, classId);
      setPublication(await api.getPublication(documentId));
      say(strings.stoppedSharing);
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  return (
    <div className="account-page">
      <p>
        <Link href="/library">{strings.backToLibrary}</Link>
      </p>
      <h1>{strings.shareHeading(title)}</h1>
      {notice}

      <section className="account-section card" aria-labelledby="shared-with">
        <h2 id="shared-with">{strings.sharedWithHeading}</h2>
        {publication?.stale ? <p className="notice notice-warn">{strings.staleShare}</p> : null}
        {!publication || publication.class_ids.length === 0 ? (
          <p>{strings.notShared}</p>
        ) : (
          <ul className="class-list">
            {publication.class_ids.map((classId) => (
              <li key={classId} className="class-item">
                <h3>{nameOf(classId)}</h3>
                <p>{strings.basisName(publication.basis)}</p>
                <button className="btn btn-quiet" type="button" onClick={() => void stop(classId)}>
                  {strings.stopSharingNamed(nameOf(classId))}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {publication && publication.class_ids.length > 0 ? (
        <PrerenderSection documentId={documentId} />
      ) : null}

      <form className="account-page" onSubmit={publish} noValidate>
        <section className="account-section card" aria-labelledby="review-heading">
          <h2 id="review-heading">{strings.reviewHeading}</h2>
          {review.pages.length === 0 ? (
            <p>{strings.noReview}</p>
          ) : (
            <>
              <p>{strings.reviewIntro}</p>
              <p className="hint">{strings.undecidedCount(review.undecided)}</p>
              {review.pages.map((page) => {
                const label = page.page_label ?? String(page.page_index + 1);
                return (
                  <fieldset key={page.page_index} className="decision">
                    <legend>{`${strings.pageWord} ${label}`}</legend>
                    {page.notes.map((line) => (
                      <p key={line} className="hint">
                        {line}
                      </p>
                    ))}
                    {(["accepted", "withheld"] as const).map((decision) => (
                      <label key={decision} className="check-row">
                        <input
                          type="radio"
                          name={`page-${page.page_index}`}
                          checked={page.decision === decision}
                          onChange={() => void decide(page.page_index, decision)}
                        />
                        {decision === "accepted" ? strings.pageAccept : strings.pageWithhold}
                      </label>
                    ))}
                  </fieldset>
                );
              })}
            </>
          )}
        </section>

        <section className="account-section card" aria-labelledby="basis-heading">
          <h2 id="basis-heading">{strings.basisHeading}</h2>
          <fieldset className="decision">
            <legend>{strings.basisIntro}</legend>
            {BASES.map((option) => (
              <label key={option} className="check-row">
                <input
                  type="radio"
                  name="basis"
                  checked={basis === option}
                  onChange={() => setBasis(option)}
                />
                {strings.basisName(option)}
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor={noteId}>{strings.basisNoteLabel}</label>
            <textarea
              id={noteId}
              aria-describedby={noteHintId}
              maxLength={500}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
            <p className="hint" id={noteHintId}>
              {strings.basisNoteHint}
            </p>
          </div>
        </section>

        <section className="account-section card" aria-labelledby="classes-heading">
          <h2 id="classes-heading">{strings.shareClassesLegend}</h2>
          {classes.length === 0 ? (
            <p>
              {strings.noClassesToShare} <Link href="/classes">{strings.classesNav}</Link>
            </p>
          ) : (
            <fieldset className="decision">
              <legend className="visually-hidden">{strings.shareClassesLegend}</legend>
              {classes.map((room) => (
                <label key={room.class_id} className="check-row">
                  <input
                    type="checkbox"
                    checked={chosen.has(room.class_id)}
                    onChange={(event) => {
                      const next = new Set(chosen);
                      if (event.target.checked) next.add(room.class_id);
                      else next.delete(room.class_id);
                      setChosen(next);
                    }}
                  />
                  {room.name}
                </label>
              ))}
            </fieldset>
          )}
          <button className="btn btn-primary" type="submit" aria-busy={busy}>
            {strings.publishAction}
          </button>
        </section>
      </form>
    </div>
  );
}
