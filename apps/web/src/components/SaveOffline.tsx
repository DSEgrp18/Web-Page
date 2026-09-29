"use client";

import Link from "next/link";
import { useState } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { offlineSupported, saveChapter } from "@/lib/offline";
import { useStrings } from "@/components/LocaleProvider";

/**
 * Save the chapter around this page for listening without a network. Only
 * sentences that already have audio can be saved; the result says how many
 * did not, so a gap offline is never a surprise.
 */
export function SaveOffline({ documentId, page }: { documentId: string; page: number }) {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  if (!offlineSupported()) return null;

  async function save() {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      const manifest = await api.offlineManifest(documentId, page);
      if (manifest.ready === 0) {
        setFailure(strings.offlineNoneVoiced);
        return;
      }
      say(strings.offlineSaving);
      await saveChapter(manifest, (done, total) =>
        setProgress(strings.offlineProgress(done, total)),
      );
      const said = strings.offlineSaved(manifest.ready, manifest.total);
      setProgress(said);
      say(said);
    } catch (error) {
      setFailure(explain(error, {}, strings));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notice-actions">
      <button
        className="btn btn-quiet btn-sm"
        type="button"
        aria-busy={busy}
        onClick={() => void save()}
      >
        {strings.offlineSave}
      </button>
      <Link className="btn btn-quiet btn-sm" href="/offline">
        {strings.offlineNav}
      </Link>
      {progress ? <p className="hint">{progress}</p> : null}
      {notice}
    </div>
  );
}
