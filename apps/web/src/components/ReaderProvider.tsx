"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { AuthApi, ReaderApi, type ClientOptions } from "@/lib/client";
import type { Account, SignedIn } from "@/lib/types";

/**
 * Who is signed in, and the client to act as them.
 *
 * The session itself is an httpOnly cookie, so this never holds it and could
 * not: it asks the API who the cookie belongs to (`/auth/me`) when the page
 * loads, and keeps what the answer says, the account and the page's CSRF
 * token, in memory only. Anything a script can store, a script injected into
 * the page can read.
 */
export type SessionStatus = "loading" | "signed_in" | "signed_out";

interface ReaderValue {
  status: SessionStatus;
  /** Shorthand for `status === "signed_in"`. */
  signedIn: boolean;
  account: Account | null;
  api: ReaderApi;
  signIn: (email: string, password: string) => Promise<SignedIn>;
  register: (email: string, password: string, displayName: string) => Promise<SignedIn>;
  recover: (email: string, recoveryCode: string, newPassword: string) => Promise<SignedIn>;
  signOut: () => Promise<void>;
}

const ReaderContext = createContext<ReaderValue | null>(null);

export function useReader(): ReaderValue {
  const value = useContext(ReaderContext);
  if (!value) throw new Error("useReader must be used inside ReaderProvider");
  return value;
}

/**
 * Offline audio belongs to whoever downloaded it, and phones are shared.
 * Everything this site cached goes when its reader signs out.
 */
async function clearOfflineCaches(): Promise<void> {
  try {
    if (typeof caches === "undefined") return;
    for (const name of await caches.keys()) await caches.delete(name);
  } catch {
    // A browser without Cache Storage, or one that refuses it, has nothing to clear.
  }
}

export function ReaderProvider({
  children,
  clientOptions,
}: {
  children: ReactNode;
  /** Tests pass a fetch implementation here; production uses the browser's. */
  clientOptions?: ClientOptions;
}) {
  const auth = useMemo(() => new AuthApi(clientOptions), [clientOptions]);
  // One client for the life of the page; the session's token is set on it.
  const api = useMemo(() => new ReaderApi(null, clientOptions), [clientOptions]);
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await auth.me();
        if (cancelled) return;
        api.setCsrf(me?.csrf ?? null);
        setAccount(me?.account ?? null);
        setStatus(me ? "signed_in" : "signed_out");
      } catch {
        // Offline or failing: nothing can be shown as this reader, and the
        // signed-out screen is where they can try again.
        if (!cancelled) setStatus("signed_out");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, api]);

  const begin = useCallback(
    (signedIn: SignedIn) => {
      api.setCsrf(signedIn.csrf_token);
      setAccount(signedIn.account);
      setStatus("signed_in");
      return signedIn;
    },
    [api],
  );

  const signIn = useCallback(
    async (email: string, password: string) => begin(await auth.signIn(email, password)),
    [auth, begin],
  );
  const register = useCallback(
    async (email: string, password: string, displayName: string) =>
      begin(await auth.register(email, password, displayName)),
    [auth, begin],
  );
  const recover = useCallback(
    async (email: string, recoveryCode: string, newPassword: string) =>
      begin(await auth.recover(email, recoveryCode, newPassword)),
    [auth, begin],
  );

  const signOut = useCallback(async () => {
    try {
      const csrf = api.csrfToken;
      if (csrf) await auth.signOut(csrf);
    } finally {
      // Signed out here whatever the server said: a reader who pressed "sign
      // out" on a shared phone must not be left signed in by a network error.
      await clearOfflineCaches();
      api.setCsrf(null);
      setAccount(null);
      setStatus("signed_out");
    }
  }, [auth, api]);
  const value = useMemo(
    () => ({
      status,
      signedIn: status === "signed_in",
      account,
      api,
      signIn,
      register,
      recover,
      signOut,
    }),
    [status, account, api, signIn, register, recover, signOut],
  );

  return <ReaderContext.Provider value={value}>{children}</ReaderContext.Provider>;
}
