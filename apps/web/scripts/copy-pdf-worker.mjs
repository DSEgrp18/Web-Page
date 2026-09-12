/**
 * Put pdf.js's runtime files where the browser can fetch them.
 *
 * pdf.js parses and renders on a Web Worker, and the worker has to be loaded
 * from a URL rather than bundled — `GlobalWorkerOptions.workerSrc` is a path,
 * not a module. So one file has to exist under `public/`.
 *
 * Copied at build time instead of committed, because the worker and the library
 * must be the exact same version: pdf.js refuses to run a worker whose version
 * does not match the API, and a committed copy silently goes stale the next
 * time anybody bumps the dependency. This runs from `predev` and `prebuild`, so
 * there is no step to remember and no way for the two to drift.
 *
 * The copy is gitignored for the same reason.
 *
 * ## standard_fonts, which is not optional for real books
 *
 * A PDF may reference one of the 14 standard fonts — Helvetica, Times, Courier
 * — without embedding it, and then pdf.js needs its own substitutes to draw the
 * page. Without `standardFontDataUrl` pointing at these files it throws
 * "Ensure that the standardFontDataUrl API parameter is provided" and the page
 * comes out blank or missing text. It costs 804 KiB, fetched only for documents
 * that actually need it.
 *
 * cmaps are deliberately *not* copied: they are 1.5 MiB and exist for CJK
 * encodings, which Sinhala textbooks do not use. Add them if a real document
 * turns up that needs them.
 */

import { copyFileSync, cpSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const version = JSON.parse(
  readFileSync(join(app, "node_modules/pdfjs-dist/package.json"), "utf8"),
).version;

const from = join(app, "node_modules/pdfjs-dist/build/pdf.worker.min.mjs");
const to = join(app, "public/pdf.worker.min.mjs");

mkdirSync(dirname(to), { recursive: true });
copyFileSync(from, to);

cpSync(
  join(app, "node_modules/pdfjs-dist/standard_fonts"),
  join(app, "public/pdf-standard-fonts"),
  {
    recursive: true,
  },
);

console.log(`pdf.js ${version} -> public/pdf.worker.min.mjs + public/pdf-standard-fonts/`);
