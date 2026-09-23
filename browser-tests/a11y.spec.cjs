const { test, expect } = require("@playwright/test");
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
  await page.addInitScript(() => localStorage.setItem("sinhala-reader.identity", "browser-tester"));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: HEADERS });
      return;
    }
    const { pathname } = new URL(request.url());
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

async function contrastAudit(page) {
  await page.addStyleTag({ content: FLAT });
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
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

const SCREENS = [
  { name: "the library", path: "/", ready: (page) => page.getByRole("heading", { name: "පොත.pdf" }) },
  {
    name: "the reader",
    path: "/documents/doc-1",
    ready: (page) => page.getByRole("button", { name: "සිංහල පොත කියවන්න." }),
  },
  { name: "bookmarks", path: "/bookmarks", ready: (page) => page.getByText("පාඩම") },
];

for (const scheme of ["light", "dark"]) {
  for (const screen of SCREENS) {
    test(`${screen.name} has no detectable violations in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await withOneBook(page);
      await page.goto(screen.path);
      await expect(screen.ready(page)).toBeVisible();

      const { violations, undecided, measured } = await contrastAudit(page);
      expect(violations).toEqual([]);
      expect(undecided).toEqual([]);
      expect(measured).toBeGreaterThan(0);
    });
  }
}

test("the contrast check fails on text a reader could not see", async ({ page }) => {
  await withOneBook(page);
  await page.goto("/");
  await expect(SCREENS[0].ready(page)).toBeVisible();
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
