import { NextResponse, type NextRequest } from "next/server";

/**
 * A returning reader goes straight to their books.
 *
 * `/` is the front door for someone new. A reader who has signed in before
 * should never have to get past it, so a visitor carrying the session cookie
 * is sent to `/library` before anything renders. Only the cookie's presence is
 * checked: this runs before the API is asked anything, and a cookie that has
 * expired simply meets the library's own sign-in panel.
 */
export const SESSION_COOKIE = "__Host-swara_session";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/library", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/"] };
