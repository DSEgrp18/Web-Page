"use client";

import type { ReactNode } from "react";

import { AnnouncerProvider } from "@/components/Announcer";
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
  return (
    <PreferencesProvider>
      <AnnouncerProvider>
        <ReaderProvider>{children}</ReaderProvider>
      </AnnouncerProvider>
    </PreferencesProvider>
  );
}
