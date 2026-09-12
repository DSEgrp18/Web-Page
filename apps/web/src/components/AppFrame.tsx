"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState, type ReactNode } from "react";

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
 * It also holds the identity step. Nothing is fetched before there is an
 * identity to fetch it as, so gating here means no screen has to handle a
 * "signed out" state of its own.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { owner } = useReader();
  const pathname = usePathname();

  // The workspace manages its own full-height layout and its own back link.
  const isWorkspace = /^\/documents\/[^/]+$/.test(pathname ?? "");

  return (
    <>
      <a className="skip-link" href="#main">
        {strings.skipToContent}
      </a>
      <div className="shell">
        <header className="shell-header">
          <div className="shell-header-inner">
            <BrandMark />

            {owner ? (
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
                  <IdentityBadge />
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
          {/* The identity comes from an external store, so a returning reader
              gets their own screen in the first client render rather than a
              flash of the sign-in form stealing the announcement. */}
          {owner ? children : <IdentityForm />}
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

function IdentityBadge() {
  const { owner, setOwner } = useReader();
  return (
    <p className="identity-badge">
      <span className="identity-name">{owner}</span>
      <button type="button" className="btn btn-quiet btn-sm" onClick={() => setOwner("")}>
        {strings.identityChange}
      </button>
    </p>
  );
}

/**
 * Not a login, and it says so where a reader will read it rather than in fine
 * print. A student uploading a private textbook must not think a name in a box
 * protects them.
 */
function IdentityForm() {
  const { setOwner } = useReader();
  const [value, setValue] = useState("");
  const inputId = useId();
  const helpId = useId();

  return (
    <div className="identity-screen">
      <img
        className="identity-art"
        src="/brand/swara-book.webp"
        alt=""
        width={700}
        height={450}
        loading="eager"
        decoding="async"
      />
      <form
        className="identity-form card"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim()) setOwner(value);
        }}
      >
        <h2>{strings.identityHeading}</h2>
        <div className="field">
          <label htmlFor={inputId}>{strings.identityLabel}</label>
          <input
            id={inputId}
            name="owner"
            value={value}
            autoComplete="username"
            aria-describedby={helpId}
            onChange={(event) => setValue(event.target.value)}
          />
          <p className="hint" id={helpId}>
            {strings.identityHelp}
          </p>
        </div>
        <button className="btn btn-primary" type="submit" disabled={!value.trim()}>
          {strings.identitySave}
        </button>
      </form>
    </div>
  );
}
