/**
 * The reader's language, on the server: from the cookie the language setting
 * writes. Server components and `generateMetadata` use this; client
 * components use `useStrings()`, which the root layout seeds from the same
 * cookie, so both render the same words and hydration has nothing to fix.
 */

import { cookies } from "next/headers";

import { LOCALE_COOKIE, parseLocale, stringsFor, type Locale } from "./i18n";
import type { Strings } from "./strings";

export async function getLocale(): Promise<Locale> {
  return parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}

export async function getStrings(): Promise<Strings> {
  return stringsFor(await getLocale());
}
