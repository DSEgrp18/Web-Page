"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/**
 * One rule for every route: after a navigation the reader asked for, focus
 * the page heading (audit F42). A cold load leaves focus alone — the screen
 * reader is already announcing the page.
 *
 * The previous path is remembered on the module, not the component, so
 * signing in (public layout unmounts, app layout mounts) still counts as
 * navigation rather than a first paint.
 */
let lastPath: string | null = null;

/** Tests share a module; a leftover path would steal focus on the next mount. */
export function resetRouteFocusForTests(): void {
  lastPath = null;
}

function focusRouteHeading(): void {
  const heading = document.querySelector<HTMLElement>("#main h1");
  const target = heading ?? document.getElementById("main");
  if (!target) return;
  if (!target.hasAttribute("tabindex")) target.tabIndex = -1;
  target.focus();
}

export function RouteFocus() {
  const pathname = usePathname() ?? "";

  useEffect(() => {
    const previous = lastPath;
    lastPath = pathname;
    if (previous === null || previous === pathname) return;
    focusRouteHeading();
  }, [pathname]);

  return null;
}
