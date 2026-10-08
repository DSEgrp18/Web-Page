"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/BrandMark";
import { RouteFocus } from "@/components/RouteFocus";
import { useReader } from "@/components/ReaderProvider";
import { Settings } from "@/components/Settings";
import { useStrings } from "@/components/LocaleProvider";
import type { Strings } from "@/lib/strings";

/** The public pages, in the order a newcomer would want them. */
const publicLinks = (strings: Strings): [href: string, label: string][] => [
  ["/how-it-works", strings.howItWorksNav],
  ["/for-teachers", strings.forTeachersNav],
  ["/help", strings.helpNav],
];

/** What every page owes a reader, one link away from anywhere. */
const footerLinks = (strings: Strings): [href: string, label: string][] => [
  ["/accessibility", strings.accessibilityNav],
  ["/privacy", strings.privacyNav],
  ["/terms", strings.termsNav],
];

/**
 * The footer both frames share. The accessibility statement, privacy notice
 * and terms are reachable from every page of the site, including the reader:
 * a reader who hits a barrier mid-chapter should not have to leave the app to
 * find out how to report it.
 */
export function SiteFooter() {
  const strings = useStrings();
  const pathname = usePathname();
  return (
    <footer className="shell-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          {/* The mark again, quietly. Decorative: the masthead link already
              names the site. */}
          <img
            className="brand-lockup brand-lockup-light"
            src="/brand/swara-lockup.webp"
            alt=""
            width={528}
            height={140}
            loading="lazy"
            decoding="async"
          />
          <img
            className="brand-lockup brand-lockup-dark"
            src="/brand/swara-lockup-dark.webp"
            alt=""
            width={528}
            height={140}
            loading="lazy"
            decoding="async"
          />
          <p className="footer-note">{strings.footerNote}</p>
        </div>
        <nav className="footer-col" aria-labelledby="footer-guide">
          <p className="footer-label" id="footer-guide">
            {strings.footerGuide}
          </p>
          <ul className="footer-links">
            {publicLinks(strings).map(([href, label]) => (
              <li key={href}>
                <Link href={href} aria-current={pathname === href ? "page" : undefined}>
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav className="footer-col" aria-labelledby="footer-statements">
          <p className="footer-label" id="footer-statements">
            {strings.footerNavigation}
          </p>
          <ul className="footer-links">
            {footerLinks(strings).map(([href, label]) => (
              <li key={href}>
                <Link href={href} aria-current={pathname === href ? "page" : undefined}>
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="footer-base">
        <p>
          <span>{strings.appName}</span>
          <span className="latin" lang="en">
            {strings.appNameLatin}
          </span>
        </p>
      </div>
    </footer>
  );
}

/**
 * The frame of the public site: the same skip link, masthead and footer as
 * the app, but no session gate, since everything here is for anyone.
 *
 * The masthead's last word depends on who is looking: a signed-in reader gets
 * a way back to their books, anyone else the way in.
 */
export function PublicFrame({ children }: { children: ReactNode }) {
  const strings = useStrings();
  const { status } = useReader();
  const pathname = usePathname();

  return (
    <>
      <RouteFocus />
      <a className="skip-link" href="#main">
        {strings.skipToContent}
      </a>
      <div className="shell">
        <header className="shell-header">
          <div className="shell-header-inner">
            <BrandMark />
            <nav className="shell-nav" aria-label={strings.publicNavigation}>
              {publicLinks(strings).map(([href, label]) => (
                <Link
                  key={href}
                  className="nav-link"
                  href={href}
                  aria-current={pathname === href ? "page" : undefined}
                >
                  {label}
                </Link>
              ))}
            </nav>
            <div className="shell-actions">
              <Settings />
              {status === "signed_in" ? (
                <Link className="btn btn-primary btn-sm" href="/library">
                  {strings.libraryHeading}
                </Link>
              ) : (
                <>
                  <Link className="btn btn-quiet btn-sm" href="/sign-in">
                    {strings.signInAction}
                  </Link>
                  <Link className="btn btn-primary btn-sm" href="/register">
                    {strings.registerHeading}
                  </Link>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Focusable from script, so the skip link's jump lands in it. */}
        <main id="main" tabIndex={-1} className="shell-main">
          {children}
        </main>

        <SiteFooter />
      </div>
    </>
  );
}
