/**
 * The browser tests' API: the site's own /api, as a signed-in reader sees it.
 *
 * The app talks only to its own origin, and learns who is signed in from
 * /api/auth/me, so that is answered here. Everything else goes to the test's
 * handler, which sees the API's own paths (without /api) through `apiUrl`.
 */

const ACCOUNT = {
  user_id: "usr-browser",
  email: "reader@example.lk",
  display_name: "කියවන්නා",
  role: "student",
  has_recovery_code: true,
  created_at: "2026-09-01T00:00:00Z",
};

const CSRF = "browser-test-csrf";

/** The request's URL with the /api prefix taken off, as the API would see it. */
function apiUrl(request) {
  const url = new URL(request.url());
  url.pathname = url.pathname.replace(/^\/api(?=\/)/, "");
  return url;
}

async function mockApi(page, handler) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    if (!new URL(request.url()).pathname.startsWith("/api/")) return route.continue();
    if (apiUrl(request).pathname === "/auth/me") {
      return route.fulfill({ status: 200, json: { ...ACCOUNT, csrf_token: CSRF } });
    }
    return handler(route);
  });
}

module.exports = { ACCOUNT, CSRF, apiUrl, mockApi };
