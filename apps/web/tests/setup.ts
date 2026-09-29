/**
 * jsdom has no media pipeline and no object URLs, so both are supplied here.
 *
 * `play()` is a stub that resolves and fires `loadeddata`, which is exactly the
 * part the player depends on: that playing starts, and that a seek can be
 * applied once data exists. It is **not** a claim that audio decodes, that the
 * sample rate is right, or that anything is audible. Those are answered by the
 * API's own audio tests and, ultimately, by a person listening.
 */

import { cleanup } from "@testing-library/react";
import { resetPreferences } from "../src/lib/preferences";
import { createElement, type AnchorHTMLAttributes, type ReactNode } from "react";
import { afterEach, vi } from "vitest";

// `next/link` needs an App Router mounted above it, which these tests do not
// have and do not need. What matters about a link is where it points, and that
// a screen reader can tell which book it opens — both survive this.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    createElement("a", { href, ...rest }, children),
}));

// `next/navigation` needs an App Router too. The path is where the test put
// the window; navigations are recorded rather than performed, so a test can
// check where a screen sent the reader.
export const navigations: string[] = [];
vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({
    push: (href: string) => navigations.push(href),
    replace: (href: string) => navigations.push(href),
    back: () => navigations.push("back"),
    refresh: () => {},
    prefetch: () => Promise.resolve(),
  }),
  // As Next's does, it ends the render: nothing after it runs.
  redirect: (href: string) => {
    navigations.push(href);
    throw new Error(`NEXT_REDIRECT ${href}`);
  },
}));

// `next/headers` needs a request. Server components read the reader's
// language from a cookie; a test sets it here, and each test starts without
// one, which is Sinhala, the default.
export const requestCookies = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      requestCookies.has(name) ? { name, value: requestCookies.get(name)! } : undefined,
  }),
}));

// `next/font/google` needs the Next runtime; tests only need the CSS variables.
vi.mock("next/font/google", () => {
  const face = (variable: string) => () => ({ className: "", variable, style: {} });
  return {
    Abhaya_Libre: face("--font-display"),
    Noto_Sans_Sinhala: face("--font-ui"),
    Roboto: face("--font-latin"),
  };
});

let objectUrls = 0;
export const revokedUrls: string[] = [];

URL.createObjectURL = vi.fn(() => `blob:test/${(objectUrls += 1)}`);
URL.revokeObjectURL = vi.fn((url: string) => {
  revokedUrls.push(url);
});

/** Every `play()` the interface attempted, so a test can assert on silence. */
export const playCalls: string[] = [];

/** The elements it was attempted on, so a test can end a clip the way a browser does. */
export const playedElements: HTMLMediaElement[] = [];

Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  writable: true,
  value: function play(this: HTMLMediaElement) {
    playCalls.push(this.src);
    playedElements.push(this);
    // Real browsers fire this once enough of the clip has arrived; the player
    // applies a saved offset here, so tests need it to happen.
    queueMicrotask(() => this.dispatchEvent(new Event("loadeddata")));
    return Promise.resolve();
  },
});

Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  writable: true,
  value: function pause() {},
});

Object.defineProperty(HTMLMediaElement.prototype, "load", {
  configurable: true,
  writable: true,
  value: function load() {},
});

// jsdom's currentTime setter throws; the player sets it on seek and on stop.
// One value backs every element, which is enough: the player owns exactly one.
let currentTime = 0;

/** Pretend the reader is this many seconds into the current sentence. */
export function setCurrentTime(seconds: number): void {
  currentTime = seconds;
}
Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
  configurable: true,
  get: () => currentTime,
  set: (value: number) => {
    currentTime = value;
  },
});

Object.defineProperty(HTMLMediaElement.prototype, "preservesPitch", {
  configurable: true,
  writable: true,
  value: true,
});

// jsdom has no pointer capture. The dividers take the pointer on
// `pointerdown` so a fast drag cannot outrun them; here that is a no-op, as
// it is in a browser when nothing moves.
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = function setPointerCapture() {};
  Element.prototype.releasePointerCapture = function releasePointerCapture() {};
  Element.prototype.hasPointerCapture = function hasPointerCapture() {
    return false;
  };
}

/** Every `scrollIntoView` call, so follow-reading tests can assert without a layout engine. */
export const scrollIntoViewCalls: Array<{
  behavior?: ScrollBehavior;
  block?: ScrollLogicalPosition;
}> = [];

HTMLElement.prototype.scrollIntoView = function scrollIntoView(
  arg?: boolean | ScrollIntoViewOptions,
) {
  if (typeof arg === "object" && arg !== null) {
    scrollIntoViewCalls.push({ behavior: arg.behavior, block: arg.block });
  } else {
    scrollIntoViewCalls.push({});
  }
};

/**
 * jsdom has no IntersectionObserver, and book covers wait on one.
 *
 * This one reports "visible" immediately, because the alternative — never
 * firing — would make every cover silently do nothing and the tests would pass
 * while asserting on a component that had not run. Tests that care about
 * laziness assert on the *requests made*, not on the observer.
 */
class ImmediateIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: ReadonlyArray<number> = [];
  private readonly callback: IntersectionObserverCallback;

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element): void {
    this.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      this as IntersectionObserver,
    );
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

globalThis.IntersectionObserver ??=
  ImmediateIntersectionObserver as unknown as typeof IntersectionObserver;

window.matchMedia =
  window.matchMedia ??
  function matchMedia(query: string): MediaQueryList {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  };

// jsdom implements `<dialog>` but not always a working `showModal` / `close`.
//
// And not the part that matters most to a keyboard: while a modal dialog is
// open, everything outside it is inert, so `focus()` on an element outside it
// does nothing. Without that, a dialog that hands focus back *before* it has
// closed passes here and drops focus to <body> in every browser — which is
// exactly what the rename dialog did.
const modalDialogs = new WeakSet<HTMLDialogElement>();
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
    modalDialogs.add(this);
  };
  const focus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function focusUnlessInert(
    this: HTMLElement,
    options?: FocusOptions,
  ) {
    const blocking = [...document.querySelectorAll("dialog[open]")].find(
      (dialog) => modalDialogs.has(dialog as HTMLDialogElement) && !dialog.contains(this),
    );
    if (blocking) return;
    focus.call(this, options);
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  Object.defineProperty(HTMLDialogElement.prototype, "open", {
    configurable: true,
    get(this: HTMLDialogElement) {
      return this.hasAttribute("open");
    },
    set(this: HTMLDialogElement, value: boolean) {
      if (value) this.setAttribute("open", "");
      else this.removeAttribute("open");
    },
  });
}

// The HTML focus fixup rule: when the focused element stops being focusable —
// here, when it is disabled — focus goes to <body>. Browsers do this and jsdom
// does not, so a control that disables itself under the reader's focus (stop,
// bookmark, ask) passed here while throwing a keyboard reader to the top of
// the page in every browser.
new MutationObserver(() => {
  const focused = document.activeElement as HTMLButtonElement | null;
  if (focused && focused !== document.body && focused.disabled) focused.blur();
}).observe(document, { attributes: true, attributeFilter: ["disabled"], subtree: true });

afterEach(() => {
  cleanup();
  playCalls.length = 0;
  playedElements.length = 0;
  revokedUrls.length = 0;
  scrollIntoViewCalls.length = 0;
  currentTime = 0;
  window.localStorage.clear();
  navigations.length = 0;
  requestCookies.clear();
  window.history.replaceState(null, "", "/");
  // The preferences module caches its snapshot for the life of the module,
  // which outlives every test. Clearing storage alone would leave the next
  // test reading what this one saved.
  resetPreferences();
});
