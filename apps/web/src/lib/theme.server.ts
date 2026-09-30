/**
 * The reader's theme, on the server, from the cookie the settings write. The
 * root layout puts it on `<html data-theme>` so the first paint is right.
 */

import { cookies } from "next/headers";

import { parseTheme, THEME_COOKIE, type Theme } from "./preferences";

export async function getTheme(): Promise<Theme> {
  return parseTheme((await cookies()).get(THEME_COOKIE)?.value);
}
