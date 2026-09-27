/*
 * Swara's service worker. Written by hand, and deliberately small.
 *
 * It does one thing: when the network is gone, it serves the offline listening
 * page (/offline) and the app's own static files from the cache they were put
 * in when a chapter was saved. It never caches anything on its own initiative,
 * never touches the API, and never serves a stale page while the network works:
 * saved audio is read by the page itself, from a cache cleared on sign-out.
 */

const SHELL = "swara-shell-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function isShell(url) {
  return (
    url.pathname === "/offline" ||
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/brand/")
  );
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !isShell(url)) return;
  event.respondWith(
    fetch(request).catch(async () => {
      const cache = await caches.open(SHELL);
      // A navigation to /offline may carry a query; the saved page has none.
      const found = (await cache.match(request)) || (await cache.match(url.pathname));
      return found || Response.error();
    }),
  );
});
