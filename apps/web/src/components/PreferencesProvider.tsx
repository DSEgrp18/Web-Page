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
   * The server renders with no `data-theme`, so a reader who chose dark gets
   * one paint of light before this runs. The alternative is a blocking inline
   * script in `<head>`, which is the usual fix and which this deliberately does
   * not do: it costs a render-blocking script on every page load to save one
   * frame, and `color-scheme` already keeps the browser's own chrome from
   * flashing white.
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
