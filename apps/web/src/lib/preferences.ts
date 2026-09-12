/**
 * What the reader has set, and wants kept.
 *
 * Written as an external store for the same reason as `identity.ts`: these
 * values live in `localStorage`, which does not exist while Next renders on the
 * server. `useSyncExternalStore` lets the server render the defaults and the
 * browser correct them in the first client render, rather than flashing the
 * wrong theme and then swapping it.
 *
 * Theme is applied to `<html data-theme>` rather than kept only in React, so
 * the whole CSS token set switches at once. `system` removes the attribute
 * entirely and lets `prefers-color-scheme` decide — which is why the dark
 * blocks in `globals.css` are written both ways.
 *
 * **The sound default is a decision, not an oversight.** A page-turn sound
 * competes directly with a screen reader speaking, so it is off until somebody
 * asks for it.
 */

export type Theme = "system" | "light" | "dark";

export interface Preferences {
  theme: Theme;
  /** Multiplier on reading text only. The interface stays put. */
  textScale: number;
  /** Scroll the reading panel to the sentence being narrated. */
  followSentence: boolean;
  /** Keep the two panels on the same page. */
  syncPages: boolean;
  /** Off by default: it competes with screen-reader speech. */
  pageTurnSound: boolean;
  /** How much width the original-PDF panel gets, 20-80. */
  splitPercent: number;
}

export const TEXT_SCALES = [0.9, 1, 1.15, 1.3, 1.5] as const;

export const DEFAULTS: Preferences = {
  theme: "system",
  textScale: 1,
  followSentence: true,
  syncPages: true,
  pageTurnSound: false,
  splitPercent: 50,
};

const KEY = "swara.preferences";

const listeners = new Set<() => void>();

/** `useSyncExternalStore` compares by identity, so the snapshot is cached. */
let snapshot: Preferences | null = null;

function read(): Preferences {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    return sanitise(parsed);
  } catch {
    // Unparseable, or storage is blocked. Defaults are always usable.
    return DEFAULTS;
  }
}

/**
 * Anything stored could have been written by an older version of this app, or
 * edited by hand. Every field is checked rather than trusted, because a bad
 * `textScale` would render the book at 40 times its size with no way back.
 */
function sanitise(value: Partial<Preferences>): Preferences {
  const theme: Theme =
    value.theme === "light" || value.theme === "dark" || value.theme === "system"
      ? value.theme
      : DEFAULTS.theme;
  const scale = TEXT_SCALES.includes(value.textScale as (typeof TEXT_SCALES)[number])
    ? (value.textScale as number)
    : DEFAULTS.textScale;
  return {
    theme,
    textScale: scale,
    followSentence: value.followSentence ?? DEFAULTS.followSentence,
    syncPages: value.syncPages ?? DEFAULTS.syncPages,
    pageTurnSound: value.pageTurnSound ?? DEFAULTS.pageTurnSound,
    // Clamped, not trusted. A stored 5000 would leave the reading panel a few
    // pixels wide with no visible way to get it back.
    splitPercent:
      typeof value.splitPercent === "number" && Number.isFinite(value.splitPercent)
        ? Math.max(20, Math.min(80, Math.round(value.splitPercent)))
        : DEFAULTS.splitPercent,
  };
}

export function subscribePreferences(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function preferencesSnapshot(): Preferences {
  if (snapshot === null) snapshot = read();
  return snapshot;
}

/**
 * Forget the cached snapshot, so the next read comes from storage again.
 *
 * Only tests need this. In a browser the module lives exactly as long as the
 * page does, and the cache is what makes `useSyncExternalStore` stable. But a
 * test run shares one module across every test, so clearing `localStorage`
 * between them would otherwise leave one test reading the settings the
 * previous test saved.
 */
export function resetPreferences(): void {
  snapshot = null;
  applyTheme("system");
}

export function serverPreferencesSnapshot(): Preferences {
  return DEFAULTS;
}

export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]): void {
  const next = { ...preferencesSnapshot(), [key]: value };
  snapshot = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // No storage: the choice still holds for this session, in memory.
  }
  applyTheme(next.theme);
  for (const listener of listeners) listener();
}

/**
 * `system` removes the attribute rather than writing "system", so the CSS
 * media query is what answers. Writing the word would need a third set of
 * rules that resolve it, which is the same thing with more to go wrong.
 */
export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
}
