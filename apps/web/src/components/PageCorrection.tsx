"use client";

import { useId, useState, type FormEvent } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { explain, useFailure } from "@/components/AccountForms";
import type { Page } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";

/** Replace flagged page text after review; bumps the document version on the server. */
export function PageCorrection({
  documentId,
  page,
  onSaved,
}: {
  documentId: string;
  page: Page;
  onSaved: (page: Page) => void;
}) {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const fieldId = useId();
  const initial = page.segments.map((segment) => segment.display_text).join("\n\n");
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);

  if (page.quality !== "needs_review") return null;

  // Saving the text as it stands would label unreviewed OCR as corrected.
  const unchanged = text.trim().split(/\s+/).join(" ") === initial.trim().split(/\s+/).join(" ");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (unchanged) {
      setFailure(strings.pageCorrectionUnchanged);
      return;
    }
    setBusy(true);
    try {
      const saved = await api.correctPage(documentId, page.page_index, text.trim());
      setFailure(null);
      onSaved(saved);
      say(strings.pageCorrected);
    } catch (error) {
      setFailure(explain(error, {}, strings));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="account-section card" onSubmit={(event) => void submit(event)} noValidate>
      <h2>{strings.pageCorrectionHeading}</h2>
      <p className="hint">{strings.pageCorrectionIntro}</p>
      {notice}
      <label htmlFor={fieldId}>{strings.pageCorrectionLabel}</label>
      <textarea
        id={fieldId}
        className="field"
        lang="si"
        rows={8}
        value={text}
        onChange={(event) => setText(event.target.value)}
        required
      />
      <button
        className="btn btn-primary"
        type="submit"
        disabled={busy}
        aria-disabled={busy || unchanged || undefined}
      >
        {strings.savePageCorrection}
      </button>
    </form>
  );
}
