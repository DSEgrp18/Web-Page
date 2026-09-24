"use client";

import { useEffect, useId, useState } from "react";

import { API_BASE } from "@/lib/client";
import { strings } from "@/lib/strings";
import type { Readiness } from "@/lib/types";

/**
 * What this server sends outside itself, as it is configured right now.
 *
 * The privacy notice is a static page, and the same page is served by every
 * deployment, so it cannot know whether this one sends page text to Google.
 * The server can: `/readiness` reports the adapters it actually started with,
 * and this reads it rather than promising something that may not be true here.
 */
export function ProcessingNow({ fetchImpl }: { fetchImpl?: typeof fetch } = {}) {
  const [state, setState] = useState<Readiness | "checking" | "unknown">("checking");
  const headingId = useId();

  useEffect(() => {
    let cancelled = false;
    const doFetch = fetchImpl ?? globalThis.fetch.bind(globalThis);
    doFetch(`${API_BASE}/readiness`, { credentials: "same-origin" })
      .then((response) => (response.ok ? (response.json() as Promise<Readiness>) : null))
      .then((readiness) => {
        if (!cancelled) setState(readiness ?? "unknown");
      })
      .catch(() => {
        if (!cancelled) setState("unknown");
      });
    return () => {
      cancelled = true;
    };
  }, [fetchImpl]);

  return (
    <section aria-labelledby={headingId} className="processing-now card">
      <h2 id={headingId}>{strings.processingNowHeading}</h2>
      {state === "checking" ? (
        <p aria-busy="true">{strings.processingNowChecking}</p>
      ) : state === "unknown" ? (
        <p>{strings.processingNowUnknown}</p>
      ) : (
        <dl className="account-details">
          <dt>{strings.processingStructure}</dt>
          <dd>
            {state.structure === "gemini" ? strings.processingGoogle : strings.processingHere}
          </dd>
          <dt>{strings.processingAnswers}</dt>
          <dd>{state.answers === "gemini" ? strings.processingGoogle : strings.processingHere}</dd>
          <dt>{strings.processingOcr}</dt>
          <dd>{state.ocr === "off" ? strings.processingOff : strings.processingHere}</dd>
        </dl>
      )}
    </section>
  );
}
