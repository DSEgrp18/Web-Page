"use client";

import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { useStrings } from "@/components/LocaleProvider";

/** The API's limit, checked here too so a reader hears it before sending. */
const MAX_CHARACTERS = 200_000;

/** Paste text to be read aloud, in sections rather than pages. */
export function PasteText() {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const router = useRouter();
  const { setFailure, notice } = useFailure();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const titleId = useId();
  const textId = useId();
  const hintId = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!text.trim()) return setFailure(strings.pasteEmpty);
    if (text.length > MAX_CHARACTERS) return setFailure(strings.pasteTooLong(text.length));
    setBusy(true);
    try {
      const made = await api.pasteText(text, title);
      say(strings.pasteStarted);
      router.push(`/library/${encodeURIComponent(made.document_id)}`);
    } catch (error) {
      setFailure(explain(error, {}, strings));
      setBusy(false);
    }
  }

  return (
    <div className="account-page">
      <h1>{strings.pasteHeading}</h1>
      <p className="hint" id={hintId}>
        {strings.pasteHow}
      </p>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor={titleId}>{strings.pasteTitleLabel}</label>
          <input
            id={titleId}
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={textId}>{strings.pasteTextLabel}</label>
          <textarea
            id={textId}
            rows={12}
            lang="si"
            aria-describedby={hintId}
            required
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </div>
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.pasteAction}
        </button>
      </form>
    </div>
  );
}
