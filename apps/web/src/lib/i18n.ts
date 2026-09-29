/**
 * Which language the interface speaks.
 *
 * Sinhala is the primary language and the default; English is optional
 * (CLAUDE.md). The choice is a cookie rather than browser storage because the
 * server has to know it before it sends a byte: `<html lang>` decides which
 * voice a screen reader uses for the whole page, and a page rendered in one
 * language and switched to the other after it loads is read out wrongly and
 * flashes for everyone else.
 *
 * The book is never translated. Its text is marked `lang="si"` wherever it
 * appears, whichever language the controls around it are in.
 */

import { si, type Strings } from "./strings";
import { en } from "./strings.en";

export type Locale = "si" | "en";

export const DEFAULT_LOCALE: Locale = "si";

/** Read by the server on every request; written by the language setting. */
export const LOCALE_COOKIE = "swara-lang";

/** Each language named in itself, so a reader who cannot read the other can find theirs. */
export const LOCALES: readonly { id: Locale; name: string }[] = [
  { id: "si", name: "සිංහල" },
  { id: "en", name: "English" },
];

/** Anything but a language this interface has is the default. */
export function parseLocale(value: string | null | undefined): Locale {
  return value === "en" ? "en" : DEFAULT_LOCALE;
}

export function stringsFor(locale: Locale): Strings {
  return locale === "en" ? en : si;
}
