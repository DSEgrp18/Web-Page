#!/usr/bin/env node
/**
 * Check `src/lib/types.ts` against the API's own OpenAPI schema.
 *
 * The types are written by hand. That is a deliberate choice — a generator is
 * one more tool to install, run, and keep in the loop — but a hand-written
 * contract drifts silently, and the way it fails is the worst kind: the API
 * renames `page_label`, the interface reads `undefined`, and a reader is told
 * the printed page number is missing on every page of the book.
 *
 * So the drift is checked instead of prevented. This does not validate types,
 * only names: that every field the server sends has somewhere to land, and that
 * the interface asks for nothing the server does not send.
 *
 * Two ways to run it:
 *
 *   node scripts/verify-contract.mjs path/to/openapi.json
 *   READER_API=http://127.0.0.1:8000 node scripts/verify-contract.mjs
 *
 * The first needs no server. From the repository root:
 *
 *   PYTHONPATH=services/api/src:services/worker/src:services/tts/src \
 *     python -c "import json;from sinhala_reader import create_app;\
 *       print(json.dumps(create_app().openapi()))" > /tmp/openapi.json
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TYPES = path.join(HERE, "..", "src", "lib", "types.ts");

/** OpenAPI schema name → the interface in `types.ts` that receives it. */
const MAPPING = {
  Box: "Box",
  SegmentDetail: "Segment",
  PageDetail: "Page",
  JobStatus: "Job",
  DocumentSummary: "DocumentSummary",
  DocumentDetail: "DocumentDetail",
  AudioManifest: "AudioManifest",
  ProgressDetail: "Progress",
  BookmarkDetail: "Bookmark",
  StudyCitation: "StudyCitation",
  StudyAnswer: "StudyAnswer",
};

/**
 * Fields the interface knowingly does not take.
 *
 * `model_text` is the romanised ASCII the synthesiser eats. The API does not
 * expose it and the browser must never show or index it; if it ever appears in
 * the schema, that is a finding, not a field to add here.
 */
const DELIBERATELY_ABSENT = new Set();

/** Routes the interface calls. A rename here is a 404 in a reader's hands. */
const REQUIRED_PATHS = [
  ["post", "/documents"],
  ["get", "/documents"],
  ["get", "/documents/{document_id}"],
  ["delete", "/documents/{document_id}"],
  ["get", "/documents/{document_id}/pages/{page_index}"],
  ["get", "/documents/{document_id}/segments/{segment_id}"],
  ["get", "/documents/{document_id}/segments/{segment_id}/audio"],
  ["get", "/documents/{document_id}/segments/{segment_id}/audio/manifest"],
  ["post", "/documents/{document_id}/questions"],
  ["post", "/documents/{document_id}/bookmarks"],
  ["get", "/documents/{document_id}/bookmarks"],
  ["delete", "/documents/{document_id}/bookmarks/{bookmark_id}"],
  ["put", "/documents/{document_id}/progress"],
  ["get", "/documents/{document_id}/progress"],
  ["get", "/readiness"],
];

async function loadSchema() {
  const [argument] = process.argv.slice(2);
  if (argument) return JSON.parse(await readFile(argument, "utf8"));

  const base = (process.env.READER_API ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
  const response = await fetch(`${base}/openapi.json`);
  if (!response.ok) throw new Error(`${base}/openapi.json responded ${response.status}`);
  return response.json();
}

/** The field names declared directly on one interface, plus what it extends. */
function fieldsOf(source, name, seen = new Set()) {
  if (seen.has(name)) return new Set();
  seen.add(name);

  const declaration = new RegExp(
    `export interface ${name}(?:\\s+extends\\s+([\\w,\\s]+?))?\\s*\\{([\\s\\S]*?)\\n\\}`,
  ).exec(source);
  if (!declaration) throw new Error(`types.ts declares no interface ${name}`);

  const fields = new Set();
  for (const parent of (declaration[1] ?? "").split(",")) {
    const trimmed = parent.trim();
    if (trimmed) for (const field of fieldsOf(source, trimmed, seen)) fields.add(field);
  }
  for (const match of declaration[2].matchAll(/^\s{2}(\w+)\??:/gm)) fields.add(match[1]);
  return fields;
}

const problems = [];

const schema = await loadSchema();
const source = await readFile(TYPES, "utf8");
const components = schema.components?.schemas ?? {};

for (const [schemaName, interfaceName] of Object.entries(MAPPING)) {
  const component = components[schemaName];
  if (!component) {
    problems.push(`The API no longer publishes a schema called ${schemaName}.`);
    continue;
  }
  const served = new Set(Object.keys(component.properties ?? {}));
  const declared = fieldsOf(source, interfaceName);

  for (const field of served) {
    if (!declared.has(field) && !DELIBERATELY_ABSENT.has(field)) {
      problems.push(`${interfaceName} has nowhere to put ${schemaName}.${field}.`);
    }
  }
  for (const field of declared) {
    if (!served.has(field)) {
      problems.push(`${interfaceName}.${field} is not something ${schemaName} sends.`);
    }
  }
}

for (const [method, route] of REQUIRED_PATHS) {
  if (!schema.paths?.[route]?.[method]) {
    problems.push(`The API no longer serves ${method.toUpperCase()} ${route}.`);
  }
}

if (problems.length > 0) {
  console.error("The reader interface and the API disagree:\n");
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error("\nFix src/lib/types.ts, or the API, depending on which one is right.");
  process.exit(1);
}

console.log(
  `Contract OK: ${Object.keys(MAPPING).length} schemas and ${REQUIRED_PATHS.length} routes match.`,
);
