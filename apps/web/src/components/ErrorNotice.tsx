"use client";

import { strings } from "@/lib/strings";

/**
 * A failure, shown on the page.
 *
 * This is deliberately **not** a live region. The error was already announced
 * assertively by the announcer at the moment it happened; making this a second
 * live region would say everything twice, and a reader who hears every error
 * twice stops trusting that two errors means two errors.
 *
 * It is here so the message stays available to read, and so the recovery
 * action — retry, dismiss — is a real focusable control rather than an
 * announcement that has already gone past.
 */
export function ErrorNotice({
  message,
  onRetry,
  onDismiss,
}: {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <div className="notice notice-bad">
      <h2>{strings.errorHeading}</h2>
      <p>{message}</p>
      {onRetry || onDismiss ? (
        <div className="notice-actions">
          {onRetry ? (
            <button type="button" className="btn btn-primary" onClick={onRetry}>
              {strings.retry}
            </button>
          ) : null}
          {onDismiss ? (
            <button type="button" className="btn btn-quiet" onClick={onDismiss}>
              {strings.dismiss}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
