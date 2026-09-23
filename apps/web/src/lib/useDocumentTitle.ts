"use client";

import { useEffect } from "react";

import { strings } from "@/lib/strings";

/**
 * Name the browser tab after something only the browser knows, such as a book.
 *
 * Most routes export static `metadata`, which is how Next sets a title. A book's
 * name cannot be known that way: it is private, and is fetched in the browser
 * with the reader's identity. So the route declares a generic title and this
 * replaces it once the name is known, in the same `%s — ස්වර` form as the root
 * layout's template, so every tab reads alike.
 *
 * `document.title` rather than React's `<title>` element. The route's metadata
 * already renders a `<title>`, and a second one leaves which of the two the
 * browser shows undefined. Navigating away needs no clean-up: Next sets the next
 * route's title itself.
 *
 * `null` leaves the title alone, for the moment before the name has arrived.
 */
export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (title) {
      document.title = `${title} — ${strings.appName}`;
    }
  }, [title]);
}
