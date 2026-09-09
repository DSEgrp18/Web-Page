"use client";

import type { ReactNode } from "react";

import { AnnouncerProvider } from "@/components/Announcer";
import { ReaderProvider } from "@/components/ReaderProvider";

/**
 * The composition root for the browser, mirroring `Deps` in the API: everything
 * replaceable is chosen once, here.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <AnnouncerProvider>
      <ReaderProvider>{children}</ReaderProvider>
    </AnnouncerProvider>
  );
}
