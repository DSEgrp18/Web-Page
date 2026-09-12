"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";

import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";

/**
 * The frame every screen sits in: a skip link, one masthead, one `<main>`.
 *
 * It also holds the identity step. Nothing is fetched before there is an
 * identity to fetch it as, so gating here means no screen has to handle a
 * "logged out" state of its own.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { owner } = useReader();

  return (
    <>
      <a className="skip-link" href="#main">
        අන්තර්ගතයට යන්න
      </a>
      <div className="app-shell">
        <aside className="app-sidebar" aria-label={strings.appName}>
          <Link className="brand" href="/">
            <h1 className="brand-name">{strings.appName}</h1>
            <span className="brand-tagline">{strings.appTagline}</span>
          </Link>
          <nav aria-label={strings.appName}>
            <Link className="sidebar-link" href="/">
              {strings.libraryHeading}
            </Link>
          </nav>
          <p className="sidebar-note">{strings.appTagline}</p>
        </aside>

        <div className="app-content">
          <header className="masthead">
            <Link className="mobile-brand" href="/">
              {strings.appName}
            </Link>
            {owner ? <IdentityBadge /> : null}
          </header>
          <main id="main" className="page-content">
            {/* The identity comes from an external store, so a returning reader
              gets their own screen in the first client render rather than a
              flash of the sign-in form stealing the announcement. */}
            {owner ? children : <IdentityForm />}
          </main>
        </div>
      </div>
    </>
  );
}

function IdentityBadge() {
  const { owner, setOwner } = useReader();
  return (
    <p className="identity-badge">
      <span className="identity-name">{owner}</span>
      <button type="button" onClick={() => setOwner("")}>
        {strings.identityChange}
      </button>
    </p>
  );
}

function IdentityForm() {
  const { setOwner } = useReader();
  const [value, setValue] = useState("");
  const inputId = useId();
  const helpId = useId();

  return (
    <form
      className="identity-form panel"
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
        {/* Said plainly, not in fine print: this is not a login. A student
            uploading a private textbook must not think it protects them. */}
        <p className="hint" id={helpId}>
          {strings.identityHelp}
        </p>
      </div>
      <button className="primary" type="submit" disabled={!value.trim()}>
        {strings.identitySave}
      </button>
    </form>
  );
}
