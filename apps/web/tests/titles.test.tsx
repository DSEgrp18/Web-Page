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
 * the routes whose titles are known before anything is fetched — in both
 * interface languages, since each title comes from the reader's language
 * cookie.
 */

import type { Metadata } from "next";
import { describe, expect, it } from "vitest";

import { LOCALE_COOKIE, stringsFor, type Locale } from "../src/lib/i18n";
import { requestCookies } from "./setup";

import { generateMetadata as root } from "../src/app/layout";
import { generateMetadata as account } from "../src/app/(app)/account/page";
import { generateMetadata as bookmarks } from "../src/app/(app)/bookmarks/page";
import { generateMetadata as reading } from "../src/app/(app)/library/[id]/page";
import { generateMetadata as library } from "../src/app/(app)/library/page";
import { generateMetadata as accessibility } from "../src/app/(public)/accessibility/page";
import { generateMetadata as forTeachers } from "../src/app/(public)/for-teachers/page";
import { generateMetadata as help } from "../src/app/(public)/help/page";
import { generateMetadata as howItWorks } from "../src/app/(public)/how-it-works/page";
import { generateMetadata as landing } from "../src/app/(public)/page";
import { generateMetadata as privacy } from "../src/app/(public)/privacy/page";
import { generateMetadata as terms } from "../src/app/(public)/terms/page";
import { generateMetadata as recover } from "../src/app/(public)/recover/page";
import { generateMetadata as register } from "../src/app/(public)/register/page";
import { generateMetadata as signIn } from "../src/app/(public)/sign-in/page";
import { generateMetadata as notFound } from "../src/app/not-found";

const ROUTES: Record<string, () => Promise<Metadata>> = {
  library,
  bookmarks,
  reading,
  account,
  signIn,
  register,
  recover,
  landing,
  howItWorks,
  forTeachers,
  help,
  accessibility,
  privacy,
  terms,
  notFound,
};

/**
 * The title a tab will actually show.
 *
 * A plain string is filled into the root layout's `%s — ස්වර` template. The
 * landing page shares the root's segment, where the template does not apply,
 * so it spells the whole title out with `absolute`; see its page.
 */
function titleOf(metadata: Metadata, appName: string): string {
  const { title } = metadata;
  if (typeof title === "string") return `${title} — ${appName}`;
  const absolute = (title as { absolute?: string } | undefined)?.absolute;
  expect(absolute, "a route title is a string, or spelled out with `absolute`").toBeTypeOf(
    "string",
  );
  return absolute as string;
}

/** Every route's metadata, as a request in this language gets it. */
async function titlesIn(locale: Locale | undefined) {
  // The cookie `getLocale()` reads, as a request carrying it would.
  if (locale) requestCookies.set(LOCALE_COOKIE, locale);
  const entries = await Promise.all(
    Object.entries(ROUTES).map(async ([route, make]) => [route, await make()] as const),
  );
  return { entries, root: await root() };
}

describe.each([
  ["Sinhala, the default, with no cookie", undefined, "si"],
  ["Sinhala, chosen", "si", "si"],
  ["English", "en", "en"],
] as const)("page titles in %s", (_name, cookie, locale) => {
  const { appName } = stringsFor(locale);

  it("gives every route a title", async () => {
    const { entries } = await titlesIn(cookie);
    for (const [route, metadata] of entries) {
      expect(titleOf(metadata, appName).trim(), route).not.toBe("");
    }
  });

  it("gives no two routes the same title", async () => {
    const { entries } = await titlesIn(cookie);
    const titles = entries.map(([, metadata]) => titleOf(metadata, appName));

    expect(new Set(titles).size).toBe(titles.length);
  });

  it("never falls back to the product's name alone", async () => {
    const { entries, root: layout } = await titlesIn(cookie);
    const fallback = (layout.title as { default: string }).default;

    for (const [, metadata] of entries) {
      expect(titleOf(metadata, appName)).not.toBe(fallback);
    }
  });

  it("says which product every page is in", async () => {
    const { entries } = await titlesIn(cookie);
    for (const [route, metadata] of entries) {
      expect(titleOf(metadata, appName), route).toMatch(new RegExp(` — ${appName}$`));
    }
  });

  it("is in the language the cookie asked for", async () => {
    const { entries } = await titlesIn(cookie);
    const sinhala = /[඀-෿]/;
    for (const [route, metadata] of entries) {
      const title = titleOf(metadata, appName);
      if (locale === "si") expect(title, route).toMatch(sinhala);
      else expect(title, route).not.toMatch(sinhala);
    }
  });
});
