/**
 * Every page has a title of its own (WCAG 2.4.2, Page Titled).
 *
 * The root layout declares a template, `%s — ස්වර`, but no route ever filled in
 * the `%s`, so every tab read the product's name and nothing else. A
 * screen-reader user switching tabs, or landing on a page, heard the same words
 * everywhere and had to explore the page to learn where they were.
 *
 * The reader's title is the book's own name, which is private and fetched in the
 * browser, so it is set once the book loads; see the reader tests. These check
 * the routes whose titles are known before anything is fetched.
 */

import type { Metadata } from "next";
import { describe, expect, it } from "vitest";

import { strings } from "../src/lib/strings";

import { metadata as root } from "../src/app/layout";
import { metadata as library } from "../src/app/page";
import { metadata as bookmarks } from "../src/app/bookmarks/page";
import { metadata as reading } from "../src/app/documents/[id]/page";
import { metadata as study } from "../src/app/documents/[id]/study/page";

const ROUTES: Record<string, Metadata> = { library, bookmarks, reading, study };

/**
 * The title a tab will actually show.
 *
 * A plain string is filled into the root layout's `%s — ස්වර` template. The
 * library shares the root's segment, where the template does not apply, so it
 * spells the whole title out with `absolute`; see its page.
 */
function titleOf(metadata: Metadata): string {
  const { title } = metadata;
  if (typeof title === "string") return `${title} — ${strings.appName}`;
  const absolute = (title as { absolute?: string } | undefined)?.absolute;
  expect(absolute, "a route title is a string, or spelled out with `absolute`").toBeTypeOf(
    "string",
  );
  return absolute as string;
}

describe("page titles", () => {
  it("gives every route a title", () => {
    for (const [route, metadata] of Object.entries(ROUTES)) {
      expect(titleOf(metadata).trim(), route).not.toBe("");
    }
  });

  it("gives no two routes the same title", () => {
    const titles = Object.values(ROUTES).map(titleOf);

    expect(new Set(titles).size).toBe(titles.length);
  });

  it("never falls back to the product's name alone", () => {
    const fallback = (root.title as { default: string }).default;

    for (const metadata of Object.values(ROUTES)) {
      expect(titleOf(metadata)).not.toBe(fallback);
    }
  });

  it("says which product every page is in", () => {
    for (const [route, metadata] of Object.entries(ROUTES)) {
      expect(titleOf(metadata), route).toMatch(new RegExp(` — ${strings.appName}$`));
    }
  });
});
