"use client";

import { useEffect, useId, useState } from "react";

import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type { ResetNotice } from "@/lib/types";

const WHEN = new Intl.DateTimeFormat("si-LK", { dateStyle: "long", timeStyle: "short" });

/**
 * "Your teacher made a reset code for your account", on every screen until
 * the reader says they have seen it.
 *
 * A reset the student did not ask for is the one they most need to hear
 * about, so this is not a toast that times out and not a live region that
 * talks over a screen reader: it is the first thing in `<main>`, with a
 * heading to find it by, and it stays until dismissed.
 */
export function ResetNoticeBanner() {
  const { api } = useReader();
  const [notice, setNotice] = useState<ResetNotice | null>(null);
  const headingId = useId();

  useEffect(() => {
    let cancelled = false;
    api.resetNotice().then(
      (found) => {
        if (!cancelled) setNotice(found);
      },
      () => {
        // Nothing to show is the safe failure; it is asked again on the next screen.
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api]);

  if (notice === null) return null;

  async function seen() {
    try {
      await api.resetNoticeSeen();
    } catch {
      // Hidden for now either way; it comes back on the next screen if unsaved.
    }
    setNotice(null);
    // The button is about to go: put focus on the screen's heading, not the page's top.
    const heading = document.querySelector<HTMLElement>("main h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }

  return (
    <section className="notice notice-warn" aria-labelledby={headingId}>
      <h2 id={headingId}>{strings.resetNoticeHeading}</h2>
      <p>
        {strings.resetNoticeText(
          notice.teacher_name,
          WHEN.format(new Date(notice.issued_at)),
          notice.used,
        )}
      </p>
      <div className="notice-actions">
        <button className="btn" type="button" onClick={() => void seen()}>
          {strings.resetNoticeSeen}
        </button>
      </div>
    </section>
  );
}
