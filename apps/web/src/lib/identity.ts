/**
 * Who the reader is — for now.
 *
 * The API authenticates with a trusted `X-Reader-User` header and refuses to
 * serve at all unless it has been started in development mode. This module is
 * the browser half of that same stopgap, and it is deliberately small: when
 * real accounts arrive, one function is replaced and nothing else moves.
 *
 * The interface says out loud that this is not a login (`strings.identityHelp`).
 * A student uploading a private textbook must not believe they are protected by
 * something that is a name in a text box.
 *
 * It is written as an external store rather than as "read localStorage in an
 * effect" because there is no such thing as localStorage while Next renders on
 * the server. `useSyncExternalStore` is React's answer to exactly that: a value
 * that has one answer on the server and another in the browser, without a
 * render pass that shows the wrong one.
 */

const KEY = "sinhala-reader.identity";

const listeners = new Set<() => void>();

/** `useSyncExternalStore` compares snapshots by identity, so this is cached. */
let snapshot: string | null = null;

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    // Private-browsing modes throw rather than return null. A reader with no
    // storage should still be able to use the app for one session.
    return "";
  }
}

export function subscribeIdentity(onChange: () => void): () => void {
  listeners.add(onChange);
  // Another tab signing in or out counts too.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function identitySnapshot(): string {
  if (snapshot === null) snapshot = read();
  return snapshot;
}

/** On the server nobody is signed in, because there is nobody. */
export function serverIdentitySnapshot(): string {
  return "";
}

export function writeIdentity(owner: string): void {
  snapshot = owner;
  try {
    if (owner) window.localStorage.setItem(KEY, owner);
    else window.localStorage.removeItem(KEY);
  } catch {
    // No storage: the identity still holds for this session, in memory.
  }
  for (const listener of listeners) listener();
}
