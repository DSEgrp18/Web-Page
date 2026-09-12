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

import type { PDFDocumentProxy } from "pdfjs-dist";

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
 * Draw one page into a canvas at a given CSS width.
 *
 * Scaled by `devicePixelRatio` so text is not soft on a phone, and capped:
 * a 3x canvas of an A4 page at full width is large enough to be worth not
 * allocating twice.
 */
export async function renderPage(
  pdf: PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  cssWidth: number,
): Promise<{ width: number; height: number }> {
  const page = await pdf.getPage(pageNumber);
  const unscaled = page.getViewport({ scale: 1 });
  const scale = cssWidth / unscaled.width;
  const viewport = page.getViewport({ scale });

  const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;

  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser did not give us a 2D canvas.");

  await page.render({
    canvas,
    canvasContext: context,
    viewport,
    transform: [ratio, 0, 0, ratio, 0, 0],
  }).promise;
  return { width: viewport.width, height: viewport.height };
}
