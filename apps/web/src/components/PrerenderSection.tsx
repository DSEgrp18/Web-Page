"use client";

import { useEffect, useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type { PrerenderStatus } from "@/lib/types";

/** How often to look again while the voice is working, in milliseconds. */
const POLL_MS = 10_000;

/**
 * Voicing a shared book for the class ahead of time, and how far it has got.
 *
 * Progress is on the page, not announced as it moves: a count ticking in a
 * live region would talk over everything else. It is said twice, when it
 * starts and when it finishes.
 */
export function PrerenderSection({ documentId }: { documentId: string }) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [state, setState] = useState<PrerenderStatus | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getPrerender(documentId).then(
      (found) => {
        if (!cancelled) setState(found);
      },
      () => {
        // Not shared yet, or not reachable: the section waits for a start.
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, documentId]);

  useEffect(() => {
    if (!working) return;
    const timer = window.setInterval(() => {
      api.getPrerender(documentId).then(
        (found) => {
          setState(found);
          if (found.ready >= found.total) {
            setWorking(false);
            say(strings.prerenderDone);
          }
        },
        () => {},
      );
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [api, documentId, working, say]);

  async function start() {
    try {
      const found = await api.startPrerender(documentId);
      setState(found);
      setFailure(null);
      if (found.ready >= found.total) {
        say(strings.prerenderDone);
      } else {
        setWorking(true);
        say(strings.prerenderStarted);
      }
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  const done = state !== null && state.ready >= state.total;

  return (
    <section className="account-section card" aria-labelledby="prerender-heading">
      <h2 id="prerender-heading">{strings.prerenderHeading}</h2>
      {notice}
      <p>{strings.prerenderIntro}</p>
      {state ? (
        <p className="hint">
          {done ? strings.prerenderDone : strings.prerenderProgress(state.ready, state.total)}
        </p>
      ) : null}
      {done ? null : (
        <div className="notice-actions">
          <button
            className="btn btn-primary"
            type="button"
            aria-busy={working}
            onClick={() => void start()}
          >
            {strings.prerenderAction}
          </button>
        </div>
      )}
    </section>
  );
}
