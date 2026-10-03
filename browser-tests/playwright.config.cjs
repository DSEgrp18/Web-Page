const { defineConfig } = require("@playwright/test");
const path = require("path");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "*.spec.cjs",
  use: { browserName: "chromium", headless: true, baseURL: "http://127.0.0.1:3100" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
    cwd: path.resolve(__dirname, "../apps/web"),
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    // The loading screen holds five seconds after every page load; the tests
    // load hundreds of pages. At 0 it still covers a load while it is slow.
    // A dev server started by hand needs the same, or each page waits.
    env: { NEXT_PUBLIC_LOADING_MIN_MS: "0" },
  },
});
