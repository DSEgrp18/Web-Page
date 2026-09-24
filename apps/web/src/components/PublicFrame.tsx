"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/BrandMark";
import { useReader } from "@/components/ReaderProvider";
import { Settings } from "@/components/Settings";
import { strings } from "@/lib/strings";

/** The public pages, in the order a newcomer would want them. */
const PUBLIC_LINKS: [href: string, label: string][] = [
  ["/how-it-works", strings.howItWorksNav],
  ["/for-teachers", strings.forTeachersNav],
  ["/help", strings.helpNav],
];

/** What every page owes a reader, one link away from anywhere. */
const FOOTER_LINKS: [href: string, label: string][] = [
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
  const pathname = usePathname();
  return (
    <footer className="shell-footer">
      <nav aria-label={strings.footerNavigation}>
        <ul className="footer-links">
          {FOOTER_LINKS.map(([href, label]) => (
            <li key={href}>
              <Link href={href} aria-current={pathname === href ? "page" : undefined}>
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <p>{strings.footerNote}</p>
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
  const { status } = useReader();
  const pathname = usePathname();

  return (
    <>
      <a className="skip-link" href="#main">
        {strings.skipToContent}
      </a>
      <div className="shell">
        <header className="shell-header">
          <div className="shell-header-inner">
            <BrandMark />
            <nav className="shell-nav" aria-label={strings.publicNavigation}>
              {PUBLIC_LINKS.map(([href, label]) => (
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

        <main id="main" className="shell-main">
          {children}
        </main>

        <SiteFooter />
      </div>
    </>
  );
}
