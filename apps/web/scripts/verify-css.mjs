#!/usr/bin/env node
/**
 * Checks that the CSS the components ask for actually exists.
 *
 * CSS fails silently. An undefined custom property falls back to the initial
 * value, and a class with no rule does nothing; the page still builds and the
 * tests still pass. That is how the delete dialog shipped with no styling at
 * all, and its buttons below the 48 px touch target. So this checks, for
 * `src/`:
 *
 *   1. every `var(--x)` names a property that is defined somewhere: in the
 *      stylesheet, as a next/font `variable`, or as an inline style;
 *   2. every class a component writes has a rule in the stylesheet;
 *   3. colours are tokens: no hex colour outside a `:root` block, so a theme
 *      and the contrast test see every colour the page can paint;
 *   4. no block defines a custom property twice, where the second silently
 *      replaces the first for every rule that uses it.
 *
 * Classes are read from string literals inside `className`, so a class built
 * by concatenation is not seen. `KNOWN_UNSTYLED` is the debt that existed
 * when this check arrived. It may only shrink: an entry that is no longer
 * used, or that gains a rule, is reported so it can be deleted.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// The app by default; a test passes a fixture directory with its own `src/`.
const root = process.argv[2] ?? fileURLToPath(new URL("..", import.meta.url));
const src = join(root, "src");

/**
 * Classes used without a rule when this check was added. Their buttons are
 * styled; what is missing is layout.
 * Bookmarks: the screen needs design work, tracked in its own issue.
 * Study: the orphaned `/study` route, deleted in Phase 1.
 */
const KNOWN_UNSTYLED = new Map([
  [
    "src/components/Bookmarks.tsx",
    new Set([
      "bookmarks-page",
      "bookmarks-heading",
      "bookmarks-empty",
      "bookmark-groups",
      "bookmark-group",
      "bookmark-list",
      "bookmark-card",
      "bookmark-page",
      "bookmark-text",
      "bookmark-note",
      "bookmark-warning",
      "bookmark-actions",
    ]),
  ],
  [
    "src/components/Study.tsx",
    new Set([
      "study-page",
      "study-topline",
      "study-heading",
      "study-form",
      "primary",
      "study-abstained",
      "study-result",
      "study-citations",
      "study-citation",
      "study-citation-place",
      "button",
    ]),
  ],
]);

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

const files = walk(src);
const rel = (path) => relative(root, path).replaceAll("\\", "/");
const stylesheets = files.filter((f) => f.endsWith(".css"));
const components = files.filter((f) => /\.(tsx|ts)$/.test(f));

/** Blank out comments but keep line numbers. */
const stripComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));

const lineOf = (text, index) => text.slice(0, index).split("\n").length;

const problems = [];

// -- what exists ------------------------------------------------------------

const css = new Map(stylesheets.map((f) => [f, stripComments(readFileSync(f, "utf8"))]));
const code = new Map(components.map((f) => [f, readFileSync(f, "utf8")]));

const defined = new Set();
const selectors = new Set();
for (const text of css.values()) {
  for (const m of text.matchAll(/(--[\w-]+)\s*:/g)) defined.add(m[1]);
  // Class names in selectors: `.a`, `.a:hover`, `.a .b`, `:is(.a)`. A dot
  // followed by a digit is a number (`0.5rem`), not a class.
  for (const m of text.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)) selectors.add(m[1]);
}
for (const text of code.values()) {
  // next/font `variable: "--font-ui"` and inline `style={{ "--scale": … }}`.
  for (const m of text.matchAll(/variable:\s*["'](--[\w-]+)["']/g)) defined.add(m[1]);
  for (const m of text.matchAll(/["'](--[\w-]+)["']\s*:/g)) defined.add(m[1]);
}

// -- 1. custom properties ---------------------------------------------------

for (const [file, text] of [...css, ...code]) {
  for (const m of text.matchAll(/var\(\s*(--[\w-]+)/g)) {
    if (!defined.has(m[1])) {
      problems.push(`${rel(file)}:${lineOf(text, m.index)}  var(${m[1]}) is never defined`);
    }
  }
}

// -- 2. classes -------------------------------------------------------------

/** The source of each `className=` value: a string, or a balanced `{…}`. */
function* classNameValues(text) {
  for (const m of text.matchAll(/className=/g)) {
    let i = m.index + m[0].length;
    if (text[i] === '"' || text[i] === "'") {
      const end = text.indexOf(text[i], i + 1);
      yield { index: i, source: text.slice(i, end + 1) };
      continue;
    }
    if (text[i] !== "{") continue;
    let depth = 0;
    const start = i;
    for (; i < text.length; i++) {
      if (text[i] === "{") depth++;
      else if (text[i] === "}" && --depth === 0) break;
    }
    yield { index: start, source: text.slice(start, i + 1) };
  }
}

/** Class tokens in the string literals of a className expression. */
function classTokens(source) {
  const tokens = [];
  const literals = source.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g);
  for (const m of literals) {
    // In a template literal only the static text counts, not `${…}`.
    const text = (m[1] ?? m[2] ?? m[3]).replace(/\$\{[^}]*\}/g, " ");
    tokens.push(...text.split(/\s+/).filter((t) => /^-?[A-Za-z_][\w-]*$/.test(t)));
  }
  return tokens;
}

const baselineSeen = new Map([...KNOWN_UNSTYLED.keys()].map((k) => [k, new Set()]));
for (const [file, text] of code) {
  const name = rel(file);
  const allowed = KNOWN_UNSTYLED.get(name);
  for (const { index, source } of classNameValues(text)) {
    for (const token of classTokens(source)) {
      if (selectors.has(token)) continue;
      if (allowed?.has(token)) {
        baselineSeen.get(name).add(token);
        continue;
      }
      problems.push(`${name}:${lineOf(text, index)}  class "${token}" has no CSS rule`);
    }
  }
}
for (const [name, allowed] of KNOWN_UNSTYLED) {
  if (!components.some((file) => rel(file) === name)) continue;
  for (const token of allowed) {
    if (!baselineSeen.get(name).has(token)) {
      problems.push(
        `scripts/verify-css.mjs  "${token}" in ${name} is styled or unused now: remove it from KNOWN_UNSTYLED`,
      );
    }
  }
}

// -- 3. colours are tokens, and 4. defined once per block -------------------

/**
 * A token block is `:root` itself, qualified only by attributes or `:not()`:
 * `:root[data-theme="dark"]`, not `:root[data-theme="dark"] .welcome`, which
 * is an ordinary rule that happens to start at the root.
 */
const isTokenBlock = (selector) => /^:root(\[[^\]]*\]|:not\([^)]*\))*$/.test(selector);

for (const [file, text] of css) {
  // Track the selector of every open block, so a declaration knows whether
  // any enclosing block is a `:root` (the light, dark and media variants),
  // and the properties each open block has defined so far.
  const open = [];
  const props = [];
  let buffer = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "{") {
      open.push(buffer.trim());
      props.push(new Set());
      buffer = "";
    } else if (ch === "}") {
      open.pop();
      props.pop();
      buffer = "";
    } else if (ch === ";") {
      const where = `${rel(file)}:${lineOf(text, i)}`;
      const hex = buffer.match(/#[0-9a-fA-F]{3,8}\b/);
      if (hex && !open.some(isTokenBlock)) {
        problems.push(`${where}  ${hex[0]} outside a :root block: make it a token`);
      }
      const prop = buffer.match(/^\s*(--[\w-]+)\s*:/);
      if (prop && props.length) {
        const seen = props.at(-1);
        if (seen.has(prop[1])) {
          problems.push(`${where}  ${prop[1]} is defined twice in "${open.at(-1)}"`);
        }
        seen.add(prop[1]);
      }
      buffer = "";
    } else {
      buffer += ch;
    }
  }
}

if (problems.length) {
  console.error(`verify-css: ${problems.length} problem(s)\n`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(
  `verify-css: ${defined.size} properties, ${selectors.size} classes, ` +
    `${components.length} components checked`,
);
