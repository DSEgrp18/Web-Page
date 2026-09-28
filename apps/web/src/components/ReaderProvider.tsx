"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, AuthApi, ReaderApi, type ClientOptions, type FailureKind } from "@/lib/client";
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
export type SessionStatus = "loading" | "signed_in" | "signed_out" | "unavailable";

/**
 * Why the session could not be checked. Only these two: the question "who is
 * signed in" was never answered, so saying "you are signed out" would be a
 * guess, and the wrong one for a reader who is signed in and whose API is
 * restarting.
 */
export type UnavailableKind = Extract<FailureKind, "offline" | "unreachable">;

interface SessionCheck {
  next: SessionStatus;
  why: UnavailableKind | null;
  me: Awaited<ReturnType<AuthApi["me"]>>;
}

interface ReaderValue {
  status: SessionStatus;
  /** For `unavailable`: whether this browser is offline or the reader is not answering. */
  unavailable: UnavailableKind | null;
  /** Ask again who is signed in. Resolves with the status it arrived at. */
  recheck: () => Promise<SessionStatus>;
  /** Shorthand for `status === "signed_in"`. */
  signedIn: boolean;
  account: Account | null;
  api: ReaderApi;
  signIn: (email: string, password: string) => Promise<SignedIn>;
  register: (email: string, password: string, displayName: string) => Promise<SignedIn>;
  recover: (email: string, recoveryCode: string, newPassword: string) => Promise<SignedIn>;
  signOut: () => Promise<void>;
  /** Change the password, then sign straight back in with it. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  newRecoveryCode: (currentPassword: string) => Promise<string>;
  signOutEverywhere: () => Promise<void>;
  deleteAccount: (currentPassword: string) => Promise<void>;
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
  const [unavailable, setUnavailable] = useState<UnavailableKind | null>(null);

  /** Who the cookie belongs to, asked of the API. Sets nothing. */
  const ask = useCallback(async (): Promise<SessionCheck> => {
    try {
      const me = await auth.me();
      return { next: me ? "signed_in" : "signed_out", why: null, me };
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : null;
      if (kind === "offline" || kind === "unreachable") {
        // Nobody answered, so nobody said this reader is signed out.
        return { next: "unavailable", why: kind, me: null };
      }
      // The API answered, and not with an account: the signed-out screen is
      // where they can try again.
      return { next: "signed_out", why: null, me: null };
    }
  }, [auth]);

  const apply = useCallback(
    ({ next, why, me }: SessionCheck) => {
      if (next !== "unavailable") {
        api.setCsrf(me?.csrf ?? null);
        setAccount(me?.account ?? null);
      }
      setUnavailable(why);
      setStatus(next);
    },
    [api],
  );

  useEffect(() => {
    let cancelled = false;
    void ask().then((result) => {
      if (!cancelled) apply(result);
    });
    return () => {
      cancelled = true;
    };
  }, [ask, apply]);

  const recheck = useCallback(async () => {
    const result = await ask();
    apply(result);
    return result.next;
  }, [ask, apply]);

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

  /** Forget the session here: token, account, and this phone's offline audio. */
  const end = useCallback(async () => {
    await clearOfflineCaches();
    api.setCsrf(null);
    setAccount(null);
    setStatus("signed_out");
  }, [api]);

  const signOut = useCallback(async () => {
    try {
      const csrf = api.csrfToken;
      if (csrf) await auth.signOut(csrf);
    } finally {
      // Signed out here whatever the server said: a reader who pressed "sign
      // out" on a shared phone must not be left signed in by a network error.
      await end();
    }
  }, [auth, api, end]);

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await auth.changePassword(api.csrfToken ?? "", currentPassword, newPassword);
      // The change ended every session, this one too, which is its point
      // elsewhere and only an obstacle here: the reader knows the new password.
      const email = account?.email;
      if (!email) return end();
      try {
        begin(await auth.signIn(email, newPassword));
      } catch {
        await end();
      }
    },
    [auth, api, account, begin, end],
  );

  const newRecoveryCode = useCallback(
    (currentPassword: string) => auth.newRecoveryCode(api.csrfToken ?? "", currentPassword),
    [auth, api],
  );

  const signOutEverywhere = useCallback(async () => {
    await auth.signOutEverywhere(api.csrfToken ?? "");
    await end();
  }, [auth, api, end]);

  const deleteAccount = useCallback(
    async (currentPassword: string) => {
      await auth.deleteAccount(api.csrfToken ?? "", currentPassword);
      await end();
    },
    [auth, api, end],
  );
  const value = useMemo(
    () => ({
      status,
      unavailable,
      recheck,
      signedIn: status === "signed_in",
      account,
      api,
      signIn,
      register,
      recover,
      signOut,
      changePassword,
      newRecoveryCode,
      signOutEverywhere,
      deleteAccount,
    }),
    [
      status,
      unavailable,
      recheck,
      account,
      api,
      signIn,
      register,
      recover,
      signOut,
      changePassword,
      newRecoveryCode,
      signOutEverywhere,
      deleteAccount,
    ],
  );

  return <ReaderContext.Provider value={value}>{children}</ReaderContext.Provider>;
}
