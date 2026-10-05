"use client";

import { useEffect, type ReactNode } from "react";

import { AnnouncerProvider } from "@/components/Announcer";
import { LoadingProvider } from "@/components/LoadingScreen";
import { PreferencesProvider } from "@/components/PreferencesProvider";
import { ReaderProvider } from "@/components/ReaderProvider";

/**
 * The composition root for the browser, mirroring `Deps` in the API: everything
 * replaceable is chosen once, here.
 *
 * Preferences sit outermost of the three because the theme they carry applies
 * to every screen including the sign-in form, which renders before there is a
 * reader at all.
 */
export function Providers({ children }: { children: ReactNode }) {
  // Only so /offline opens without a network; see public/sw.js.
  useEffect(() => {
    navigator.serviceWorker?.register("/sw.js").catch(() => {});
  }, []);
  return (
    <PreferencesProvider>
      <AnnouncerProvider>
        <ReaderProvider>
          {/* Inside the reader's provider, so the session check can say it is
              still loading; it owns the loading screen. */}
          <LoadingProvider>{children}</LoadingProvider>
        </ReaderProvider>
      </AnnouncerProvider>
    </PreferencesProvider>
  );
}
