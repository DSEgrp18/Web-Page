"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { BrandMark } from "@/components/BrandMark";
import { ResetNoticeBanner } from "@/components/ResetNoticeBanner";
import { SiteFooter } from "@/components/PublicFrame";
import { useReader, type UnavailableKind } from "@/components/ReaderProvider";
import { Settings } from "@/components/Settings";
import { messageFor } from "@/lib/strings";
import { useStrings } from "@/components/LocaleProvider";

/**
 * The frame every screen sits in: a skip link, one masthead, one `<main>`.
 *
 * The old sidebar is gone. A permanent 9rem rail costs the same width on every
 * screen to hold two links, and the screen that matters — two panels of a book
 * side by side — is the one that can least afford it. Two links belong in the
 * masthead.
 *
 * The reading workspace opts out of the centred column entirely
 * (`shell-main-wide`), because a PDF constrained to 76rem on a wide monitor is
 * the one thing this redesign exists to stop doing.
 *
 * It also holds the session gate. Nothing is fetched before there is a
 * session to fetch it with, so gating here means no screen has to handle a
 * "signed out" state of its own. The account pages are the exception: they are
 * where a reader who is signed out goes.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const strings = useStrings();
  const { status, unavailable } = useReader();
  const pathname = usePathname() ?? "/library";

  // The workspace manages its own full-height layout and its own back link.
  const isWorkspace = /^\/library\/[^/]+$/.test(pathname);
  const signedIn = status === "signed_in";

  // Leaving the "cannot be reached" panel takes its retry button, and focus
  // with it. The sign-in panel places focus itself; the page they asked for
  // starts at the top of `<main>`.
  const main = useRef<HTMLElement>(null);
  const wasUnavailable = useRef(false);
  useEffect(() => {
    if (wasUnavailable.current && signedIn && document.activeElement === document.body) {
      main.current?.focus();
    }
    wasUnavailable.current = status === "unavailable";
  }, [status, signedIn]);

  return (
    <>
      <a className="skip-link" href="#main">
        {strings.skipToContent}
      </a>
      <div className="shell">
        <header className="shell-header">
          <div className="shell-header-inner">
            <BrandMark href={signedIn ? "/library" : "/"} />

            {signedIn ? (
              <>
                <nav className="shell-nav" aria-label={strings.primaryNavigation}>
                  <Link
                    className="nav-link"
                    href="/library"
                    aria-current={pathname === "/library" ? "page" : undefined}
                  >
                    {strings.libraryHeading}
                  </Link>
                  <Link
                    className="nav-link"
                    href="/bookmarks"
                    aria-current={pathname === "/bookmarks" ? "page" : undefined}
                  >
                    {strings.bookmarksNav}
                  </Link>
                  <Link
                    className="nav-link"
                    href="/classes"
                    aria-current={pathname.startsWith("/classes") ? "page" : undefined}
                  >
                    {strings.classesNav}
                  </Link>
                  <Link
                    className="nav-link"
                    href="/progress"
                    aria-current={pathname === "/progress" ? "page" : undefined}
                  >
                    {strings.progressNav}
                  </Link>
                  <Link
                    className="nav-link"
                    href="/offline"
                    aria-current={pathname === "/offline" ? "page" : undefined}
                  >
                    {strings.offlineNav}
                  </Link>
                </nav>
                <div className="shell-actions">
                  <Settings />
                  <AccountBadge />
                </div>
              </>
            ) : (
              <div className="shell-actions">
                <Settings />
              </div>
            )}
          </div>
        </header>

        {/* Focusable from script, so the skip link's jump lands in it. */}
        <main
          ref={main}
          id="main"
          tabIndex={-1}
          className={isWorkspace ? "shell-main shell-main-wide" : "shell-main"}
        >
          {signedIn ? (
            <>
              {/* Not over the book: the workspace owns its whole height. It
                  is on the library, where every sign-in lands. */}
              {isWorkspace ? null : <ResetNoticeBanner />}
              {children}
            </>
          ) : status === "loading" ? (
            // Short, and not announced: a reader who hears "loading" on every
            // visit learns to ignore the word.
            <p className="hint" aria-busy="true">
              {strings.loadingSession}
            </p>
          ) : status === "unavailable" && unavailable ? (
            <Unavailable kind={unavailable} />
          ) : (
            <SignedOut pathname={pathname} />
          )}
        </main>

        {isWorkspace ? null : <SiteFooter />}
      </div>
    </>
  );
}

function AccountBadge() {
  const strings = useStrings();
  const { account, signOut } = useReader();
  const { say } = useAnnouncer();
  return (
    <p className="account-badge">
      {/* The name is the way to the account page. The visible name stays
          first in the accessible name, so a voice-control user can say it. */}
      <Link className="account-name" href="/account">
        {account?.display_name}
        <span className="visually-hidden"> — {strings.accountHeading}</span>
      </Link>
      <button
        type="button"
        className="btn btn-quiet btn-sm"
        onClick={() => {
          void signOut().then(() => say(strings.signedOut));
        }}
      >
        {strings.signOut}
      </button>
    </p>
  );
}

/**
 * When nobody answered "who is signed in": this browser is offline, or the
 * reader behind the site is starting or down. Not the sign-in form, because
 * nobody said this reader is signed out, and signing in would fail the same
 * way. The page they asked for is still the address, so trying again is all
 * there is to do.
 */
function Unavailable({ kind }: { kind: UnavailableKind }) {
  const strings = useStrings();
  const { recheck } = useReader();
  const { alert } = useAnnouncer();
  const [checking, setChecking] = useState(false);
  const message = messageFor(kind, strings);

  useEffect(() => {
    const before = document.title;
    document.title = `${strings.errorHeading} — ${strings.appName}`;
    return () => {
      document.title = before;
    };
  }, [strings.appName, strings.errorHeading]);

  async function tryAgain() {
    // Not `disabled`: a disabled button under the reader's focus drops it.
    if (checking) return;
    setChecking(true);
    if ((await recheck()) === "unavailable") {
      // Still nobody there. Said out loud, or the press seems to do nothing.
      setChecking(false);
      alert(message);
    }
    // Otherwise this panel goes, and `AppFrame` puts the reader at the top of
    // the page they asked for.
  }

  return (
    <section className="account-form card" aria-labelledby="unavailable-heading">
      <h1 id="unavailable-heading" tabIndex={-1}>
        {strings.errorHeading}
      </h1>
      <p className="notice notice-bad">{message}</p>
      <button
        type="button"
        className="btn btn-primary"
        aria-disabled={checking || undefined}
        onClick={() => void tryAgain()}
      >
        {strings.retry}
      </button>
    </section>
  );
}

/**
 * Where a signed-out reader lands, on any page. Sign-in brings them back
 * here, to the page they asked for.
 */
function SignedOut({ pathname }: { pathname: string }) {
  const strings = useStrings();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    // After "sign out", the button that was pressed is gone; without this,
    // focus falls to the top of the page and the reader is nowhere.
    if (document.activeElement === document.body) heading.current?.focus();
  }, []);

  // The tab says what is on screen: "sign in", not the page that is not
  // showing. The route's own title comes back when this panel goes.
  useEffect(() => {
    const before = document.title;
    document.title = `${strings.signInHeading} — ${strings.appName}`;
    return () => {
      document.title = before;
    };
  }, [strings.appName, strings.signInHeading]);

  // The query goes too: a class link's code must survive signing in. This
  // panel only renders in the browser, once the session check has answered.
  const [search] = useState(() => (typeof window === "undefined" ? "" : window.location.search));
  const next =
    pathname === "/library" || pathname === "/"
      ? ""
      : `?next=${encodeURIComponent(pathname + search)}`;
  return (
    <div className="account-screen">
      <img
        className="account-art"
        src="/brand/swara-book.webp"
        alt=""
        width={700}
        height={450}
        loading="eager"
        decoding="async"
      />
      <section className="account-form card" aria-labelledby="signed-out-heading">
        <h1 id="signed-out-heading" ref={heading} tabIndex={-1}>
          {strings.signedOutHeading}
        </h1>
        <p>{strings.signedOutBody}</p>
        <div className="notice-actions">
          <Link className="btn btn-primary" href={`/sign-in${next}`}>
            {strings.signInAction}
          </Link>
          <Link className="btn" href="/register">
            {strings.registerHeading}
          </Link>
        </div>
      </section>
    </div>
  );
}
