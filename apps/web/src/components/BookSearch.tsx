"use client";

import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type { SearchHit, SearchResults } from "@/lib/types";

/**
 * Search inside one book. Two lists, never merged: the book's own sentences
 * containing the words, in book order, then the passages most about them.
 * A result opens the book cued at that sentence, not playing, and the saved
 * reading position is untouched until the reader plays and pauses.
 */
export function BookSearch({ documentId }: { documentId: string }) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [title, setTitle] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [busy, setBusy] = useState(false);
  const queryId = useId();
  const hintId = useId();

  useEffect(() => {
    let cancelled = false;
    api.getDocument(documentId).then(
      (book) => {
        if (!cancelled) setTitle(book.title?.trim() || book.filename);
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [api, documentId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !query.trim()) return;
    setBusy(true);
    try {
      const found = await api.searchBook(documentId, query.trim());
      setFailure(null);
      setResults(found);
      say(
        found.exact.length + found.related.length
          ? strings.searchFound(found.exact.length, found.related.length)
          : strings.searchNothing,
      );
    } catch (error) {
      setFailure(explain(error, {}));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="account-page">
      <p>
        <Link href={`/library/${encodeURIComponent(documentId)}`}>{strings.backToLibrary}</Link>
      </p>
      <h1>{strings.searchHeading(title)}</h1>
      {notice}
      <form className="account-fields" role="search" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor={queryId}>{strings.searchLabel}</label>
          <input
            id={queryId}
            type="search"
            lang="si"
            maxLength={200}
            aria-describedby={hintId}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <p className="hint" id={hintId}>
            {strings.searchHow}
          </p>
        </div>
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.searchAction}
        </button>
      </form>

      {results ? (
        results.exact.length + results.related.length === 0 ? (
          <p>{strings.searchNothing}</p>
        ) : (
          <>
            <Hits
              id="exact-heading"
              heading={strings.searchExactHeading(results.exact.length)}
              hits={results.exact}
              documentId={documentId}
            />
            <Hits
              id="related-heading"
              heading={strings.searchRelatedHeading}
              hits={results.related}
              documentId={documentId}
            />
          </>
        )
      ) : null}
    </div>
  );
}

function Hits({
  id,
  heading,
  hits,
  documentId,
}: {
  id: string;
  heading: string;
  hits: SearchHit[];
  documentId: string;
}) {
  if (hits.length === 0) return null;
  return (
    <section className="account-section card" aria-labelledby={id}>
      <h2 id={id}>{heading}</h2>
      <ol>
        {hits.map((hit) => (
          <li key={`${id}-${hit.segment_id}`}>
            <Link
              href={`/library/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(hit.segment_id)}`}
            >
              {strings.searchResultPage(hit.page_label ?? String(hit.page_index + 1))}
            </Link>
            <p lang="si">{hit.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
