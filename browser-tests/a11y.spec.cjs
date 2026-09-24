const { test, expect } = require("@playwright/test");
const { apiUrl, mockApi } = require("./session.cjs");
const { default: AxeBuilder } = require("@axe-core/playwright");

/**
 * axe over the real, rendered screens, with colour contrast on.
 *
 * The jsdom run in apps/web/tests/a11y.test.tsx has to switch contrast off:
 * jsdom has no layout and no canvas. Here Chromium paints the page, so axe
 * can measure what a reader actually sees, in both themes.
 *
 * axe cannot measure text over a gradient. It reports the node as undecided,
 * not as a violation, so a page full of gradients passes without contrast
 * ever being checked. The page's gradients are decorative tints over token
 * surfaces, so they are removed before measuring, and each element is judged
 * on its background colour. The tint's worst case is checked separately, in
 * tokens.contrast.test.ts. After that, contrast must be decided for every
 * node, and a canary below proves the check can fail at all.
 */

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
  "content-type": "application/json",
};

const JOB = {
  job_id: "job-1", kind: "prepare", state: "succeeded", stage: "extract",
  detail: null, updated_at: "2026-09-20T00:00:00Z",
};

const BOOK = {
  document_id: "doc-1", filename: "පොත.pdf", media_type: "application/pdf", title: null,
  size_bytes: 1024, created_at: "2026-09-20T00:00:00Z", version: "v1", page_count: 1,
  segment_count: 2, reading: null, notes: [], chapters: [], job: JOB,
};

const segment = (index, text) => ({
  segment_id: `0000-s${index}`, index, page_index: 0, page_label: "1",
  display_text: text, spoken_text: text, boxes: [], role: "unknown", level: null,
});

const PAGE = {
  page_index: 0, page_label: "1", kind: "text", quality: "accepted", notes: [],
  segments: [segment(0, "සිංහල පොත කියවන්න."), segment(1, "ඊළඟ වාක්‍යය මෙහි ඇත.")],
};

const BOOKMARK = {
  bookmark_id: "bm-1", document_id: "doc-1", segment_id: "0000-s0", page_index: 0,
  page_label: "1", display_text: "සිංහල පොත කියවන්න.", note: "පාඩම", stale: false,
  segment_found: true, created_at: "2026-09-20T00:00:00Z",
};

/** A signed-in reader with one prepared book, and nothing else on the API. */
async function withOneBook(page) {
  await mockApi(page, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: HEADERS });
      return;
    }
    const { pathname } = apiUrl(request);
    const body = {
      "/documents": [BOOK],
      "/documents/doc-1": BOOK,
      "/documents/doc-1/pages/0": PAGE,
      "/documents/doc-1/bookmarks": [BOOKMARK],
    }[pathname];
    await route.fulfill({
      status: body ? 200 : 404,
      headers: HEADERS,
      body: JSON.stringify(body ?? { detail: "not found" }),
    });
  });
}

const FLAT = "*, *::before, *::after { background-image: none !important; }";

/**
 * Nodes axe may leave undecided: an emoji or symbol glyph (`nonBmp`) in an
 * `aria-hidden` icon, which is decoration with no text to read.
 */
const UNDECIDABLE = new Set(["nonBmp"]);

/**
 * An overlay must be opaque: a translucent one lets the page's words show
 * through its own, which no contrast ratio covers. Once that is asserted,
 * what lies underneath cannot change what the overlay shows, so it is hidden
 * before measuring. Otherwise axe finds the page text in the stack under the
 * overlay and reports the overlay's text as undecided.
 */
async function isolate(page, overlay) {
  const background = await page
    .locator(overlay)
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(background, `${overlay} must have an opaque background`).toMatch(
    /^rgb\(|^color\(srgb [\d.]+ [\d.]+ [\d.]+\)$/,
  );
  await page.locator(overlay).evaluate((target) => {
    for (const element of document.body.querySelectorAll("*")) {
      if (!target.contains(element) && !element.contains(target)) {
        element.style.visibility = "hidden";
      }
    }
  });
}

async function contrastAudit(page, overlay) {
  await page.addStyleTag({ content: FLAT });
  let axe = new AxeBuilder({ page }).withTags(TAGS);
  if (overlay) {
    await isolate(page, overlay);
    axe = axe.include(overlay);
  }
  const results = await axe.analyze();
  const undecided = results.incomplete
    .filter((rule) => rule.id === "color-contrast")
    .flatMap((rule) => rule.nodes)
    .filter((node) => !node.any.some((check) => UNDECIDABLE.has(check.data?.messageKey)))
    .map((node) => `${node.target.join(" ")}: ${node.any.map((c) => c.message).join("; ")}`);
  const violations = results.violations.map((v) => ({
    rule: v.id,
    nodes: v.nodes.map((n) => `${n.target.join(" ")}: ${n.failureSummary}`),
  }));
  const measured = results.passes.find((rule) => rule.id === "color-contrast")?.nodes.length ?? 0;
  return { violations, undecided, measured };
}

const LIBRARY = { path: "/library", ready: (page) => page.getByRole("heading", { name: "පොත.pdf" }) };
const READER = {
  path: "/library/doc-1",
  ready: (page) => page.getByRole("button", { name: "සිංහල පොත කියවන්න." }),
};

/** Each screen, and each dialog or panel opened over one, as its own state. */
const SCREENS = [
  { name: "the library", ...LIBRARY },
  {
    name: "the delete dialog",
    ...LIBRARY,
    open: async (page) => {
      await page.getByRole("button", { name: /මකන්න.*පොත\.pdf/ }).click();
      await expect(page.getByRole("dialog", { name: "මෙම පොත මකන්න ද?" })).toBeVisible();
    },
    overlay: "dialog[open]",
  },
  {
    name: "the rename dialog",
    ...LIBRARY,
    open: async (page) => {
      await page.getByRole("button", { name: /නම වෙනස් කරන්න/ }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
    },
    overlay: "dialog[open]",
  },
  {
    name: "settings",
    ...LIBRARY,
    open: async (page) => {
      await page.getByRole("button", { name: "කියවීමේ සැකසුම්" }).click();
      await expect(page.getByRole("radio").first()).toBeVisible();
    },
    overlay: ".settings-panel",
  },
  { name: "the reader", ...READER },
  {
    name: "the assistant",
    ...READER,
    open: async (page) => {
      await page.getByRole("button", { name: "පොත ගැන අසන්න" }).click();
      await expect(page.getByRole("complementary", { name: "පොත ගැන අසන්න" })).toBeVisible();
    },
    overlay: ".assistant",
  },
  { name: "bookmarks", path: "/bookmarks", ready: (page) => page.getByText("පාඩම") },
  // The public site: each page has exactly one h1.
  ...[
    ["the front door", "/"],
    ["how it works", "/how-it-works"],
    ["for teachers", "/for-teachers"],
    ["help", "/help"],
    ["the accessibility statement", "/accessibility"],
    ["the privacy notice", "/privacy"],
    ["the terms", "/terms"],
  ].map(([name, path]) => ({
    name,
    path,
    ready: (page) => page.getByRole("heading", { level: 1 }),
  })),
  {
    name: "signing in",
    path: "/sign-in",
    ready: (page) => page.getByRole("heading", { name: "ඇතුළු වන්න" }),
  },
  {
    name: "the account page",
    path: "/account",
    ready: (page) => page.getByRole("heading", { name: "මගේ ගිණුම", level: 1 }),
  },
  {
    name: "making an account",
    path: "/register",
    ready: (page) => page.getByRole("heading", { name: "ගිණුමක් සාදන්න" }),
  },
];

for (const scheme of ["light", "dark"]) {
  for (const screen of SCREENS) {
    test(`${screen.name} has no detectable violations in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await withOneBook(page);
      await page.goto(screen.path);
      await expect(screen.ready(page)).toBeVisible();
      if (screen.open) await screen.open(page);

      const { violations, undecided, measured } = await contrastAudit(page, screen.overlay);
      expect(violations).toEqual([]);
      expect(undecided).toEqual([]);
      expect(measured).toBeGreaterThan(0);
    });
  }
}

test("the contrast check fails on text a reader could not see", async ({ page }) => {
  await withOneBook(page);
  await page.goto("/library");
  await expect(LIBRARY.ready(page)).toBeVisible();
  await page.evaluate(() => {
    const faint = document.createElement("p");
    faint.id = "faint";
    faint.textContent = "අඩු වෙනස";
    faint.style.color = "#b0b0b0";
    document.querySelector("main").append(faint);
  });

  const { violations } = await contrastAudit(page);
  const contrast = violations.find((v) => v.rule === "color-contrast");
  expect(contrast?.nodes.join(" ")).toContain("#faint");
});
