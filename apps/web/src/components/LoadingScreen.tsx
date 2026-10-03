"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useStrings } from "@/components/LocaleProvider";

/**
 * The loading screen: the page behind it blurred, the logo, and a voice of
 * bars moving under it.
 *
 * It covers two moments:
 *
 * - **A refresh** (any full page load). It is in the server's HTML, so it is
 *   the first thing painted, and it stays at least `FIRST_LOAD_MIN_MS` from
 *   the moment the browser began the load, and until the page has its data.
 *   Then it lifts by itself and the page is there. The owner chose five
 *   seconds and no way to skip; `NEXT_PUBLIC_LOADING_MIN_MS` overrides it, and
 *   the browser tests set it to 0 so they do not each wait five seconds.
 * - **A page loading its data** inside the app (the library, a book, classes,
 *   progress). Shown only if the wait passes `SHOW_AFTER_MS`, so a fast answer
 *   never flashes it, and then held for `SHOWN_AT_LEAST_MS` so it does not
 *   flicker. No five-second minimum here: that would make every screen slow.
 *
 * It never covers audio buffering: the reader must be able to pause and move
 * at every moment. The player shows the same bars in place instead
 * (`BrandBars`).
 *
 * While it is up, the page behind it is `inert`, so neither the keyboard nor a
 * screen reader can reach controls that cannot be seen, and its one line of
 * text is a polite status, said once.
 */

const configured = Number(process.env.NEXT_PUBLIC_LOADING_MIN_MS);
/** How long the screen stays after a refresh, at the least. */
export const FIRST_LOAD_MIN_MS = Number.isFinite(configured) && configured >= 0 ? configured : 5000;
/** A page load shorter than this never shows the screen. */
export const SHOW_AFTER_MS = 400;
/** Once shown for a page load, at least this long, so it never flickers. */
export const SHOWN_AT_LEAST_MS = 600;
/**
 * The longest the screen covers a page that is still loading. A request that
 * never answers, or a flag that is never cleared, must not trap a reader
 * behind an inert page: after this the screen lifts, and the page's own
 * loading message is there underneath.
 */
export const MAX_COVER_MS = 15000;
/** The fade out. Kept short; with reduced motion it is instant. */
const FADE_MS = 360;

interface Loading {
  /** Mark a part of the page as loading; returns the call that unmarks it. */
  begin: () => () => void;
}

const LoadingContext = createContext<Loading>({ begin: () => () => {} });

/**
 * Tell the loading screen that this page is still loading its data. Safe to
 * call anywhere: outside the provider (as in unit tests) it does nothing.
 */
export function useBusy(active: boolean): void {
  const { begin } = useContext(LoadingContext);
  useEffect(() => (active ? begin() : undefined), [active, begin]);
}

export function LoadingProvider({ children }: { children: ReactNode }) {
  // How many parts of the page are loading, and which load this is: the
  // number goes up each time loading starts from nothing, so the screen can
  // tell one slow load from the next.
  const count = useRef(0);
  const [busy, setBusy] = useState(false);
  const [load, setLoad] = useState(0);
  const begin = useCallback(() => {
    count.current += 1;
    if (count.current === 1) {
      setLoad((n) => n + 1);
      setBusy(true);
    }
    let ended = false;
    return () => {
      if (ended) return;
      ended = true;
      count.current -= 1;
      if (count.current === 0) setBusy(false);
    };
  }, []);
  const value = useMemo(() => ({ begin }), [begin]);

  return (
    <LoadingContext.Provider value={value}>
      {children}
      <LoadingScreen busy={busy} load={load} />
    </LoadingContext.Provider>
  );
}

function LoadingScreen({ busy, load }: { busy: boolean; load: number }) {
  const strings = useStrings();
  const [minimumMet, setMinimumMet] = useState(false);
  // Server and first client render agree: up, as the first paint of a load.
  const [refreshOver, setRefreshOver] = useState(false);
  // When a slow page load put the screen up, or null when it is not up for one.
  const [shownAt, setShownAt] = useState<number | null>(null);
  // The load the screen gave up on after MAX_COVER_MS: it does not come back
  // for that same load, only for the next one.
  const [gaveUpOn, setGaveUpOn] = useState(-1);
  // Still in the document: kept for the fade after it lifts.
  const [present, setPresent] = useState(true);
  const screen = useRef<HTMLDivElement>(null);

  // The refresh ends once the minimum has passed and nothing is loading.
  // Decided while rendering, React's way of adjusting state to new input.
  if (!refreshOver && minimumMet && !busy) setRefreshOver(true);

  // The refresh's minimum, counted from when the browser began the load, not
  // from when this code arrived, so a slow script does not add to it.
  useEffect(() => {
    const remaining = Math.max(0, FIRST_LOAD_MIN_MS - performance.now());
    const timer = window.setTimeout(() => setMinimumMet(true), remaining);
    return () => window.clearTimeout(timer);
  }, []);

  // A refresh whose page never finishes loading: lift anyway.
  useEffect(() => {
    if (refreshOver || !minimumMet || !busy) return;
    const timer = window.setTimeout(() => {
      setGaveUpOn(load);
      setRefreshOver(true);
    }, MAX_COVER_MS);
    return () => window.clearTimeout(timer);
  }, [refreshOver, minimumMet, busy, load]);

  // After the refresh, a page load puts the screen up only if it is slow.
  useEffect(() => {
    if (!refreshOver || !busy || shownAt !== null || gaveUpOn === load) return;
    const timer = window.setTimeout(() => setShownAt(performance.now()), SHOW_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [refreshOver, busy, shownAt, gaveUpOn, load]);

  // Up for a page load: held long enough not to flicker, never past the cap.
  useEffect(() => {
    if (shownAt === null) return;
    const elapsed = performance.now() - shownAt;
    const timer = busy
      ? window.setTimeout(
          () => {
            setGaveUpOn(load);
            setShownAt(null);
          },
          Math.max(0, MAX_COVER_MS - elapsed),
        )
      : window.setTimeout(() => setShownAt(null), Math.max(0, SHOWN_AT_LEAST_MS - elapsed));
    return () => window.clearTimeout(timer);
  }, [shownAt, busy, load]);

  const up = !refreshOver || shownAt !== null;

  // Back in the document the moment it is up again; out after the fade.
  if (up && !present) setPresent(true);
  useEffect(() => {
    if (up || !present) return;
    const timer = window.setTimeout(() => setPresent(false), FADE_MS);
    return () => window.clearTimeout(timer);
  }, [up, present]);

  // Everything else on the page is out of reach while the screen is up.
  useEffect(() => {
    const element = screen.current;
    if (!up || !element?.parentElement) return;
    const made: Element[] = [];
    for (const sibling of Array.from(element.parentElement.children)) {
      if (sibling === element || sibling.hasAttribute("inert")) continue;
      sibling.setAttribute("inert", "");
      made.push(sibling);
    }
    return () => made.forEach((sibling) => sibling.removeAttribute("inert"));
  }, [up, present]);

  if (!present) return null;

  return (
    <div
      ref={screen}
      className="loading-screen"
      data-leaving={up ? undefined : true}
      data-moment={refreshOver ? "page" : "refresh"}
    >
      <div className="loading-screen-body">
        <img
          className="loading-logo loading-logo-light"
          src="/brand/swara-logo.webp"
          alt=""
          width={480}
          height={327}
          decoding="async"
        />
        <img
          className="loading-logo loading-logo-dark"
          src="/brand/swara-logo-dark.webp"
          alt=""
          width={480}
          height={327}
          decoding="async"
        />
        <BrandBars />
        <p className="loading-message" role="status">
          {refreshOver ? strings.pageLoading : strings.loadingSession}
        </p>
      </div>
    </div>
  );
}

/**
 * Five bars in the logo's colours, rising and falling like a voice. The
 * loading screen's animation, and the player's while audio buffers.
 * Decoration: the words beside it say what is happening.
 */
export function BrandBars({ small = false }: { small?: boolean }) {
  return (
    <span className={small ? "brand-bars brand-bars-small" : "brand-bars"} aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
      <span />
    </span>
  );
}
