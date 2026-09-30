"use client";

import { createContext, useCallback, useContext, useEffect, useMemo } from "react";
import { useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import {
  applyTheme,
  preferencesSnapshot,
  serverPreferencesSnapshot,
  setPreference,
  subscribePreferences,
  type Preferences,
} from "@/lib/preferences";

interface PreferencesValue {
  preferences: Preferences;
  set: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences must be used inside PreferencesProvider");
  return value;
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const preferences = useSyncExternalStore(
    subscribePreferences,
    preferencesSnapshot,
    serverPreferencesSnapshot,
  );

  /*
   * The server already rendered `data-theme` from the theme cookie, so this
   * normally changes nothing. It matters when the two disagree — a theme saved
   * before the cookie existed, or cookies cleared — and it rewrites the
   * cookie, so the next page load is right from its first byte. No blocking
   * inline script in `<head>`: the cookie does that job without one.
   */
  useEffect(() => {
    applyTheme(preferences.theme);
  }, [preferences.theme]);

  // Reading text scales; the interface does not. A reader who needs large
  // Sinhala body text rarely wants the navigation to grow with it.
  useEffect(() => {
    document.documentElement.style.setProperty("--reading-scale", String(preferences.textScale));
  }, [preferences.textScale]);

  const set = useCallback(
    <K extends keyof Preferences>(key: K, value: Preferences[K]) => setPreference(key, value),
    [],
  );

  const value = useMemo(() => ({ preferences, set }), [preferences, set]);
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}
