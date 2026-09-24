"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { BrandMark } from "@/components/BrandMark";
import { useReader } from "@/components/ReaderProvider";
import { Settings } from "@/components/Settings";
import { strings } from "@/lib/strings";

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
/** The pages a signed-out reader can see: where they sign in. */
const ACCOUNT_PATHS = new Set(["/sign-in", "/register", "/recover"]);

export function AppFrame({ children }: { children: ReactNode }) {
  const { status } = useReader();
  const pathname = usePathname() ?? "/";

  // The workspace manages its own full-height layout and its own back link.
  const isWorkspace = /^\/documents\/[^/]+$/.test(pathname);
  const isAccountPage = ACCOUNT_PATHS.has(pathname);
  const signedIn = status === "signed_in";

  return (
    <>
      <a className="skip-link" href="#main">
        {strings.skipToContent}
      </a>
      <div className="shell">
        <header className="shell-header">
          <div className="shell-header-inner">
            <BrandMark />

            {signedIn ? (
              <>
                <nav className="shell-nav" aria-label={strings.primaryNavigation}>
                  <Link
                    className="nav-link"
                    href="/"
                    aria-current={pathname === "/" ? "page" : undefined}
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

        <main id="main" className={isWorkspace ? "shell-main shell-main-wide" : "shell-main"}>
          {isAccountPage || signedIn ? (
            children
          ) : status === "loading" ? (
            // Short, and not announced: a reader who hears "loading" on every
            // visit learns to ignore the word.
            <p className="hint" aria-busy="true">
              {strings.loadingSession}
            </p>
          ) : (
            <SignedOut pathname={pathname} />
          )}
        </main>

        {isWorkspace ? null : (
          <footer className="shell-footer">
            <p>{strings.footerNote}</p>
          </footer>
        )}
      </div>
    </>
  );
}

function AccountBadge() {
  const { account, signOut } = useReader();
  const { say } = useAnnouncer();
  return (
    <p className="account-badge">
      <span className="account-name">{account?.display_name}</span>
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
 * Where a signed-out reader lands, on any page. Sign-in brings them back
 * here, to the page they asked for.
 */
function SignedOut({ pathname }: { pathname: string }) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    // After "sign out", the button that was pressed is gone; without this,
    // focus falls to the top of the page and the reader is nowhere.
    if (document.activeElement === document.body) heading.current?.focus();
  }, []);

  const next = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
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
