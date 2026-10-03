"use client";

import { useEffect, useRef, useState } from "react";

import { useReader } from "@/components/ReaderProvider";
import { openDocument, renderPage } from "@/lib/pdf";
import { useStrings } from "@/components/LocaleProvider";

/** How wide the rendered page is, in CSS pixels. Cards are narrower; this is 2x. */
const COVER_WIDTH = 320;

/**
 * The first page of the book, as its cover.
 *
 * ## Nothing happens until the card is near the screen
 *
 * A library of twenty books must not open twenty PDFs on load. An
 * `IntersectionObserver` with a generous margin starts the render just before
 * the card scrolls into view, so covers appear as you reach them and a library
 * you never scroll costs nothing. Combined with range requests, one cover is a
 * few tens of kilobytes rather than a whole book.
 *
 * ## A missing cover is a normal state, not an error
 *
 * A book still being prepared has no useful first page; an encrypted or
 * malformed PDF may never render one. Both fall back to the brand placeholder
 * rather than an error, because a reader does not need to be told that a
 * decorative thumbnail failed — they need the card to still work.
 *
 * The canvas is `aria-hidden` and the placeholder carries no alt text for the
 * same reason: the card's heading already says which book this is, and a
 * screen reader announcing "image" before every title is noise.
 */
/** How many cover colourways there are; each book keeps the same one. */
const TONES = 6;

/** A stable colourway for a book: the same book is the same colour everywhere. */
function toneOf(documentId: string): number {
  let hash = 0;
  for (const char of documentId) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return Math.abs(hash) % TONES;
}

export function BookCover({
  documentId,
  ready,
  title,
}: {
  documentId: string;
  ready: boolean;
  /** Drawn on the cover when the book's first page cannot be. */
  title?: string;
}) {
  const strings = useStrings();
  const { signedIn } = useReader();
  const holder = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [progress, setProgress] = useState<"waiting" | "drawing" | "drawn" | "failed">("waiting");

  /*
   * Derived, not stored. A book that is still being prepared has nothing to
   * render from, and that is a fact about the props rather than something to
   * discover in an effect and write back into state — which would be a second
   * render on every card, every time the library polls.
   */
  const state = !ready || !signedIn || progress === "failed" ? "unavailable" : progress;

  useEffect(() => {
    // Nothing to draw from until preparation has produced a document.
    if (!ready || !signedIn) return;
    const element = holder.current;
    if (!element) return;

    let cancelled = false;
    let close: (() => void) | null = null;

    const draw = async () => {
      setProgress("drawing");
      try {
        const { pdf, cancel } = await openDocument(documentId);
        close = () => {
          cancel();
          void pdf.destroy();
        };
        if (cancelled) {
          close();
          return;
        }
        const target = canvas.current;
        if (!target) return;
        await renderPage(pdf, 1, target, COVER_WIDTH);
        if (!cancelled) setProgress("drawn");
      } catch {
        // Encrypted, malformed, or gone. The card still works without it.
        if (!cancelled) setProgress("failed");
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          void draw();
        }
      },
      // Start a little before it is visible, so the cover is there by the time
      // the card is.
      { rootMargin: "400px" },
    );
    observer.observe(element);

    return () => {
      cancelled = true;
      observer.disconnect();
      close?.();
    };
  }, [documentId, signedIn, ready]);

  return (
    <div className="book-cover" ref={holder} data-state={state}>
      {/* A cover of our own, from the first moment: the placeholder while the
          book's first page draws, and the cover itself when it cannot (a
          Word file, pasted text, or a PDF still being prepared). The title is
          the card's heading already, so this is decoration. */}
      {state === "drawn" ? null : (
        <div className="cover-art" data-tone={toneOf(documentId)} aria-hidden="true">
          <svg className="cover-art-mark" viewBox="0 0 48 32" focusable="false">
            <path d="M4 22 24 4l20 18" />
            <path d="M12 24c4-3 8-3 12 0 4-3 8-3 12 0" />
          </svg>
          {title ? <span className="cover-art-title">{title}</span> : null}
          <span className="cover-art-brand" lang="si">
            ස්වර
          </span>
        </div>
      )}
      {state === "unavailable" ? null : <canvas ref={canvas} aria-hidden="true" />}
      {state === "drawing" ? <span className="visually-hidden">{strings.coverLoading}</span> : null}
    </div>
  );
}
