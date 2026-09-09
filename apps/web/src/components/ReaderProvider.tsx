"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import { ReaderApi, type ClientOptions } from "@/lib/client";
import {
  identitySnapshot,
  serverIdentitySnapshot,
  subscribeIdentity,
  writeIdentity,
} from "@/lib/identity";

interface ReaderValue {
  owner: string;
  setOwner: (owner: string) => void;
  api: ReaderApi;
}

const ReaderContext = createContext<ReaderValue | null>(null);

export function useReader(): ReaderValue {
  const value = useContext(ReaderContext);
  if (!value) throw new Error("useReader must be used inside ReaderProvider");
  return value;
}

export function ReaderProvider({
  children,
  ownerOverride,
  clientOptions,
}: {
  children: ReactNode;
  /**
   * Tests pin an identity here to skip the sign-in step. An empty string means
   * "no override", so a test can still start signed out and sign in.
   */
  ownerOverride?: string;
  /** Tests pass a fetch implementation here; production uses the browser's. */
  clientOptions?: ClientOptions;
}) {
  const stored = useSyncExternalStore(subscribeIdentity, identitySnapshot, serverIdentitySnapshot);
  const owner = ownerOverride || stored;

  const setOwner = useCallback((next: string) => writeIdentity(next.trim()), []);

  const api = useMemo(() => new ReaderApi(owner, clientOptions), [owner, clientOptions]);
  const value = useMemo(() => ({ owner, setOwner, api }), [owner, setOwner, api]);

  return <ReaderContext.Provider value={value}>{children}</ReaderContext.Provider>;
}
