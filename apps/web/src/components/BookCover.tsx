"use client";

import { useEffect, useRef, useState } from "react";

import { useReader } from "@/components/ReaderProvider";
import { openDocument, renderPage } from "@/lib/pdf";
import { strings } from "@/lib/strings";

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
export function BookCover({ documentId, ready }: { documentId: string; ready: boolean }) {
  const { owner } = useReader();
  const holder = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [progress, setProgress] = useState<"waiting" | "drawing" | "drawn" | "failed">("waiting");

  /*
   * Derived, not stored. A book that is still being prepared has nothing to
   * render from, and that is a fact about the props rather than something to
   * discover in an effect and write back into state — which would be a second
   * render on every card, every time the library polls.
   */
  const state = !ready || !owner || progress === "failed" ? "unavailable" : progress;

  useEffect(() => {
    // Nothing to draw from until preparation has produced a document.
    if (!ready || !owner) return;
    const element = holder.current;
    if (!element) return;

    let cancelled = false;
    let close: (() => void) | null = null;

    const draw = async () => {
      setProgress("drawing");
      try {
        const { pdf, cancel } = await openDocument(documentId, owner);
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
  }, [documentId, owner, ready]);

  return (
    <div className="book-cover" ref={holder} data-state={state}>
      {state === "unavailable" ? (
        <img
          className="book-cover-fallback"
          src="/brand/swara-book.webp"
          alt=""
          width={700}
          height={450}
          loading="lazy"
          decoding="async"
        />
      ) : (
        <canvas ref={canvas} aria-hidden="true" />
      )}
      {state === "drawing" ? <span className="visually-hidden">{strings.coverLoading}</span> : null}
    </div>
  );
}
