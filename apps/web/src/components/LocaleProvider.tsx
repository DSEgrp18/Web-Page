"use client";

import { createContext, useContext, type ReactNode } from "react";

import { DEFAULT_LOCALE, LOCALE_COOKIE, stringsFor, type Locale } from "@/lib/i18n";
import type { Strings } from "@/lib/strings";

const LocaleContext = createContext<Locale>(DEFAULT_LOCALE);

/**
 * The reader's language, for every client component under it. The root
 * layout reads the cookie and passes it in; nothing here reads storage, so the
 * server's render and the browser's first render agree.
 */
export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

/** The words of the reader's language. */
export function useStrings(): Strings {
  return stringsFor(useLocale());
}

/** Remember a choice of language for a year. The server reads it next request. */
export function saveLocale(locale: Locale): void {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
}
