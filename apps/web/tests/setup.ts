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
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
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

afterEach(() => {
  cleanup();
  playCalls.length = 0;
  playedElements.length = 0;
  revokedUrls.length = 0;
  scrollIntoViewCalls.length = 0;
  currentTime = 0;
  window.localStorage.clear();
  // The preferences module caches its snapshot for the life of the module,
  // which outlives every test. Clearing storage alone would leave the next
  // test reading what this one saved.
  resetPreferences();
});
