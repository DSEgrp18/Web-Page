/**
 * Put pdf.js's worker where the browser can fetch it.
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
 */

import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
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

console.log(`pdf.js worker ${version} -> public/pdf.worker.min.mjs`);
