/**
 * Opening the original PDF in the browser.
 *
 * ## Why pdf.js fetches this itself instead of being handed a blob
 *
 * The obvious shape is `fetch` the file, then `getDocument({ data })`. That
 * works and it is wrong for a book: it downloads the whole PDF before the first
 * page appears, which for a 50 MB scan is 50 MB before anything is on screen.
 *
 * Given a `url`, pdf.js does its own transport: it reads the cross-reference
 * table from the end of the file with `Range: bytes=-N`, then fetches only the
 * objects each page needs. Opening page 1 of that same scan costs tens of
 * kilobytes. `httpHeaders` is how the identity travels, since there is no
 * cookie and an `<embed src>` could not carry one anyway.
 *
 * The API answers ranges and exposes `Content-Range` through CORS specifically
 * so this works. If either were missing, pdf.js would silently fall back to
 * whole-file downloads — slower, never broken, and easy to miss.
 *
 * ## The library is loaded on demand
 *
 * pdf.js is about a megabyte. Importing it at module scope would put it in the
 * bundle of every screen including the sign-in form. `loadPdfLibrary()` is a
 * dynamic import behind a cached promise, so the first screen that needs a PDF
 * pays for it and nothing else does.
 */

import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

import { API_BASE, OWNER_HEADER } from "./client";

type PdfModule = typeof import("pdfjs-dist");

let libraryPromise: Promise<PdfModule> | null = null;

export function loadPdfLibrary(): Promise<PdfModule> {
  libraryPromise ??= import("pdfjs-dist").then((pdfjs) => {
    // Copied out of node_modules by `scripts/copy-pdf-worker.mjs` at build
    // time. It must be the same version as the library — pdf.js refuses a
    // worker whose version does not match — which is why it is copied rather
    // than committed.
    pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
    return pdfjs;
  });
  return libraryPromise;
}

/** The URL the API serves a document's bytes from. */
export function documentFileUrl(documentId: string): string {
  return `${API_BASE}/documents/${encodeURIComponent(documentId)}/file`;
}

/**
 * Open a document for rendering.
 *
 * The caller owns the result and must `destroy()` it, which also cancels
 * in-flight range requests. Leaving one open holds the fetched pages and a
 * worker for the life of the tab.
 */
export async function openDocument(
  documentId: string,
  owner: string,
): Promise<{ pdf: PDFDocumentProxy; cancel: () => void }> {
  const pdfjs = await loadPdfLibrary();
  const task = pdfjs.getDocument({
    url: documentFileUrl(documentId),
    httpHeaders: { [OWNER_HEADER]: owner },
    // A PDF may reference Helvetica or Times without embedding them, and then
    // pdf.js needs its own substitutes. Without this it throws and the page
    // comes out blank — which a blind reader has no way to notice.
    standardFontDataUrl: "/pdf-standard-fonts/",
    // Identity is a header, not a cookie. Sending credentials would be a
    // different security model than the API is written for.
    withCredentials: false,
  });
  const pdf = await task.promise;
  return {
    pdf,
    cancel: () => {
      void task.destroy();
    },
  };
}

/**
 * Whatever is still drawing on each canvas.
 *
 * A `WeakMap`, so a canvas that goes out of the document takes its entry with
 * it rather than pinning a render task for the life of the tab.
 */
const inFlight = new WeakMap<HTMLCanvasElement, RenderTask>();

/**
 * Draw one page into a canvas at a given CSS width.
 *
 * ## Renders on one canvas are serialised, and that is not a nicety
 *
 * pdf.js composes its transform onto whatever the context already has — its
 * own `resetCtxToDefault` resets styles but deliberately *not* the matrix, so
 * it trusts the caller to hand over a canvas at identity. Setting
 * `canvas.width` is what provides that, because assigning to it resets the
 * context.
 *
 * Which is exactly the trap. `PdfPanel` draws from an effect *and* from a
 * `ResizeObserver`, so a second render can begin while the first is still
 * going — and the `canvas.width` line below would then reset the context out
 * from under the running one. It carries on drawing with an identity matrix
 * instead of the viewport's, and the viewport's matrix is what flips PDF's
 * y-up coordinates to the canvas's y-down. The page comes out **upside down**,
 * on some pages and not others, depending entirely on whether a second draw
 * happened to land mid-render.
 *
 * So: cancel whatever is drawing here, wait for it to actually stop, and only
 * then touch the canvas. `cancel()` alone is not enough — it resolves the task
 * asynchronously, and the window between asking and stopping is the whole bug.
 *
 * ## Device pixels come from the viewport, not a transform
 *
 * The scale is folded into `getViewport` and the CSS size set separately,
 * rather than passing a `transform` matrix. Same result, one fewer matrix to
 * compose, and nothing to get the sign of wrong.
 */
export async function renderPage(
  pdf: PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  cssWidth: number,
): Promise<{ width: number; height: number }> {
  const running = inFlight.get(canvas);
  if (running) {
    running.cancel();
    // A cancelled task rejects with RenderingCancelledException. That is the
    // expected outcome here, not a failure.
    await running.promise.catch(() => {});
  }

  const page = await pdf.getPage(pageNumber);
  const unscaled = page.getViewport({ scale: 1 });
  const cssScale = cssWidth / unscaled.width;

  // Capped at 2: a 3x canvas of a full-width A4 page is large enough to be
  // worth not allocating, and the difference is not visible.
  const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
  const viewport = page.getViewport({ scale: cssScale * ratio });

  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${Math.floor(viewport.width / ratio)}px`;
  canvas.style.height = `${Math.floor(viewport.height / ratio)}px`;

  // `canvas` only. pdf.js documents that passing `canvasContext` alongside it
  // is for backwards compatibility and that the canvas must be null to use it —
  // and it discards our context anyway, taking its own with `alpha: false`.
  const task = page.render({ canvas, viewport });
  inFlight.set(canvas, task);
  try {
    await task.promise;
  } finally {
    // Only if it is still ours: a newer render may already have claimed it.
    if (inFlight.get(canvas) === task) inFlight.delete(canvas);
  }
  return { width: viewport.width / ratio, height: viewport.height / ratio };
}
