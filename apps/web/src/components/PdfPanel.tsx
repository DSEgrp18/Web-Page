"use client";

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useReader } from "@/components/ReaderProvider";
import { openDocument, renderPage } from "@/lib/pdf";
import { strings } from "@/lib/strings";

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3] as const;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const THUMB_WIDTH = 96;

/**
 * The book as it was printed.
 *
 * ## One page at a time, deliberately
 *
 * Not a scrolling canvas of every page. A 168-page textbook rendered at once
 * is hundreds of megabytes of canvas, and the reading panel beside it shows one
 * page of sentences — so a continuous scroll on the left would have nothing to
 * stay in step with on the right. One page, matched to the other panel, is both
 * cheaper and the thing that makes the two halves mean the same thing.
 *
 * ## Rendering is cancelled, not just ignored
 *
 * pdf.js render tasks keep running after the component moves on, and two on the
 * same canvas throw. Paging quickly — which is exactly what somebody looking
 * for a figure does — would otherwise fill the console with
 * `RenderingCancelledException` and occasionally paint the wrong page. Each
 * render holds its task and cancels it on the way out.
 *
 * ## What this panel is not
 *
 * It does not highlight the sentence being narrated on the page image. Doing
 * that honestly needs a mapping from a segment to a rectangle in *this*
 * rendering, and the boxes the API returns come from pdfplumber's coordinate
 * space, not pdf.js's viewport. Guessing would put a box in the wrong place on
 * a page a blind reader cannot check, so the panel shows the page and the
 * reading panel does the highlighting.
 */
export function PdfPanel({
  documentId,
  pageIndex,
  pageCount,
  onPageChange,
}: {
  documentId: string;
  pageIndex: number;
  pageCount: number;
  onPageChange: (index: number) => void;
}) {
  const { owner } = useReader();
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [showThumbs, setShowThumbs] = useState(false);

  const viewport = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const pageInputId = useId();

  // -- open the document once --------------------------------------------

  useEffect(() => {
    if (!owner) return;
    let cancelled = false;
    let close: (() => void) | null = null;

    void (async () => {
      setState("loading");
      try {
        const opened = await openDocument(documentId, owner);
        close = () => {
          opened.cancel();
          void opened.pdf.destroy();
        };
        if (cancelled) {
          close();
          return;
        }
        setPdf(opened.pdf);
        setState("ready");
      } catch {
        if (!cancelled) setState("failed");
      }
    })();

    return () => {
      cancelled = true;
      setPdf(null);
      close?.();
    };
  }, [documentId, owner]);

  // -- draw the current page ---------------------------------------------

  const draw = useCallback(async () => {
    const target = canvas.current;
    const box = viewport.current;
    if (!pdf || !target || !box) return;
    // pdf.js pages are 1-based; everything else here is 0-based.
    const number = Math.min(Math.max(pageIndex + 1, 1), pdf.numPages);
    const available = box.clientWidth - 32;
    const width = zoom === "fit" ? available : available * zoom;
    try {
      await renderPage(pdf, number, target, Math.max(120, width));
    } catch {
      // A cancelled render is the normal outcome of paging quickly, not a
      // failure worth telling anybody about.
    }
  }, [pdf, pageIndex, zoom]);

  useEffect(() => {
    void draw();
  }, [draw]);

  // Re-fit when the divider moves or the window changes. Observing the element
  // rather than the window catches the split drag, which does not resize
  // anything the window knows about.
  useEffect(() => {
    const box = viewport.current;
    if (!box || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      // Coalesced: a drag fires this continuously, and re-rasterising a page
      // per pointer event is how a smooth drag becomes a slideshow.
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => void draw());
    });
    observer.observe(box);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [draw]);

  const stepZoom = (direction: 1 | -1) => {
    const current = zoom === "fit" ? 1 : zoom;
    const index = ZOOMS.findIndex((value) => value >= current - 0.001);
    const next = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, index + direction))];
    setZoom(next ?? 1);
  };

  return (
    <section className="panel pdf-panel" aria-label={strings.originalPanel}>
      <div className="panel-bar">
        <h2 className="panel-title">{strings.originalPanel}</h2>

        <div className="panel-tools">
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            aria-pressed={showThumbs}
            onClick={() => setShowThumbs((shown) => !shown)}
          >
            {showThumbs ? strings.hideThumbnails : strings.showThumbnails}
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-icon"
            onClick={() => stepZoom(-1)}
            disabled={zoom !== "fit" && zoom <= MIN_ZOOM}
          >
            <span aria-hidden="true">−</span>
            <span className="visually-hidden">{strings.zoomOut}</span>
          </button>
          <span className="zoom-readout latin" aria-live="off">
            {zoom === "fit" ? strings.fitWidth : `${Math.round(zoom * 100)}%`}
          </span>
          <button
            type="button"
            className="btn btn-quiet btn-icon"
            onClick={() => stepZoom(1)}
            disabled={zoom !== "fit" && zoom >= MAX_ZOOM}
          >
            <span aria-hidden="true">+</span>
            <span className="visually-hidden">{strings.zoomIn}</span>
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            aria-pressed={zoom === "fit"}
            onClick={() => setZoom("fit")}
          >
            {strings.fitWidth}
          </button>
        </div>
      </div>

      <div className="pdf-body">
        {showThumbs && pdf ? (
          <Thumbnails
            pdf={pdf}
            pageIndex={pageIndex}
            pageCount={pageCount}
            onPageChange={onPageChange}
          />
        ) : null}

        <div className="pdf-viewport" ref={viewport}>
          {state === "loading" ? (
            <p className="hint" aria-busy="true">
              {strings.pdfLoading}
            </p>
          ) : state === "failed" ? (
            <p className="notice notice-warn">{strings.pdfFailed}</p>
          ) : null}
          {/* Decorative here: the page's words are in the reading panel, as
              selectable text. Announcing "image" adds nothing a reader can use. */}
          <canvas ref={canvas} aria-hidden="true" hidden={state !== "ready"} />
        </div>
      </div>

      <div className="panel-foot">
        <PageStepper
          key={pageIndex}
          pageIndex={pageIndex}
          pageCount={pageCount}
          onPageChange={onPageChange}
          inputId={pageInputId}
        />
      </div>
    </section>
  );
}

/**
 * Page navigation.
 *
 * Keyed by page in the parent, so it remounts when the page changes elsewhere:
 * typing "40" and then pressing Next should not leave "40" sitting in the box.
 * That is what `key` is for, and it avoids copying a prop into state.
 */
function PageStepper({
  pageIndex,
  pageCount,
  onPageChange,
  inputId,
}: {
  pageIndex: number;
  pageCount: number;
  onPageChange: (index: number) => void;
  inputId: string;
}) {
  const [value, setValue] = useState(String(pageIndex + 1));

  return (
    <form
      className="page-stepper"
      onSubmit={(event) => {
        event.preventDefault();
        const wanted = Number(value);
        if (Number.isFinite(wanted)) {
          onPageChange(Math.min(Math.max(1, Math.round(wanted)), pageCount) - 1);
        }
      }}
    >
      <button
        type="button"
        className="btn btn-quiet btn-icon"
        onClick={() => onPageChange(pageIndex - 1)}
        disabled={pageIndex <= 0}
      >
        <span aria-hidden="true">‹</span>
        <span className="visually-hidden">{strings.previousPage}</span>
      </button>

      <label htmlFor={inputId} className="visually-hidden">
        {strings.goToPage}
      </label>
      <input
        id={inputId}
        className="page-number latin"
        type="number"
        inputMode="numeric"
        min={1}
        max={pageCount}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <span className="hint latin">/ {pageCount}</span>

      <button type="submit" className="btn btn-sm">
        {strings.goToPageSubmit}
      </button>

      <button
        type="button"
        className="btn btn-quiet btn-icon"
        onClick={() => onPageChange(pageIndex + 1)}
        disabled={pageIndex >= pageCount - 1}
      >
        <span aria-hidden="true">›</span>
        <span className="visually-hidden">{strings.nextPage}</span>
      </button>
    </form>
  );
}

/**
 * A strip of pages to jump between.
 *
 * Rendered in a window around the current page rather than all of them: 168
 * thumbnails is 168 canvases and 168 rasterisations, for a control somebody
 * uses to move a few pages at a time.
 */
function Thumbnails({
  pdf,
  pageIndex,
  pageCount,
  onPageChange,
}: {
  pdf: PDFDocumentProxy;
  pageIndex: number;
  pageCount: number;
  onPageChange: (index: number) => void;
}) {
  const WINDOW = 6;
  const from = Math.max(0, pageIndex - WINDOW);
  const to = Math.min(pageCount - 1, pageIndex + WINDOW);
  const pages = Array.from({ length: to - from + 1 }, (_, offset) => from + offset);

  return (
    <nav className="thumbnails" aria-label={strings.thumbnails}>
      <ol>
        {pages.map((index) => (
          <li key={index}>
            <button
              type="button"
              className="thumbnail"
              aria-current={index === pageIndex ? "page" : undefined}
              onClick={() => onPageChange(index)}
            >
              <Thumbnail pdf={pdf} pageIndex={index} />
              <span className="thumbnail-number latin">{index + 1}</span>
              <span className="visually-hidden">{strings.thumbnailGoTo(index + 1)}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Thumbnail({ pdf, pageIndex }: { pdf: PDFDocumentProxy; pageIndex: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const target = canvas.current;
      if (!target) return;
      try {
        await renderPage(pdf, pageIndex + 1, target, THUMB_WIDTH);
      } catch {
        // Cancelled or unrenderable. The number below it still navigates.
      }
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [pdf, pageIndex]);

  return <canvas ref={canvas} aria-hidden="true" />;
}
