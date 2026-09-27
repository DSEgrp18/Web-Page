const { test, expect } = require("@playwright/test");
const { apiUrl, mockApi } = require("./session.cjs");

/**
 * Layout, which only a browser that paints can check.
 *
 * Each test here is a finding from docs/ui-audit.md that jsdom could not have
 * caught: it has no layout, so a panel in a 0-wide grid track, a page that
 * scrolls sideways, and a button painted over another all pass there.
 */

const segment = (index, text) => ({
  segment_id: `0000-s${index}`, index, page_index: 0, page_label: "1",
  display_text: text, spoken_text: text, boxes: [], role: "unknown", level: null,
});

const BOOK = {
  document_id: "doc-1", filename: "පොත.pdf", media_type: "application/pdf", title: null,
  size_bytes: 1024, created_at: "2026-09-20T00:00:00Z", version: "v1", page_count: 1,
  segment_count: 2, reading: null, notes: [], chapters: [],
  job: { job_id: "job-1", kind: "prepare", state: "succeeded", stage: "extract", detail: null, updated_at: "2026-09-20T00:00:00Z" },
};

const PAGE = {
  page_index: 0, page_label: "1", kind: "text", quality: "accepted", notes: [],
  segments: [segment(0, "සිංහල පොත කියවන්න."), segment(1, "ඊළඟ වාක්‍යය මෙහි ඇත.")],
};

/** One prepared book, and a 404 for everything else. */
async function oneBook(page) {
  await mockApi(page, async (route) => {
    const path = apiUrl(route.request()).pathname;
    const body = path === "/documents" ? [BOOK]
      : path === "/documents/doc-1" ? BOOK
      : path === "/documents/doc-1/pages/0" ? PAGE
      : null;
    await route.fulfill(body ? { status: 200, json: body } : { status: 404, json: { detail: "not found" } });
  });
}

/** How far the page scrolls sideways. Zero is the only right answer. */
function sideways(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test("expanding the reading panel shows the reading panel", async ({ page }) => {
  await oneBook(page);
  await page.goto("/library/doc-1");
  const sentence = page.getByRole("button", { name: "සිංහල පොත කියවන්න." });
  await expect(sentence).toBeVisible();

  await page.getByRole("button", { name: "කියවීම විශාල කරන්න" }).click();

  // It used to land in a 0-wide grid track: present, "visible" to the
  // accessibility tree, and painted nowhere.
  await expect(sentence).toBeVisible();
  const box = await sentence.boundingBox();
  expect(box?.width).toBeGreaterThan(200);
});

test("at 300% zoom the book's text has room", async ({ page }) => {
  // A 1280 x 900 window at 300% is about 427 x 300 CSS pixels.
  await page.setViewportSize({ width: 427, height: 300 });
  await oneBook(page);
  await page.goto("/library/doc-1");
  const panel = page.locator("#panel-reading");
  await expect(page.getByRole("button", { name: "සිංහල පොත කියවන්න." })).toBeAttached();
  const box = await panel.boundingBox();
  expect(box?.height).toBeGreaterThan(100);
  expect(await sideways(page)).toBe(0);
});

for (const path of ["/library", "/library/doc-1", "/"]) {
  test(`${path} does not scroll sideways at 320 px`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await oneBook(page);
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await sideways(page)).toBe(0);
  });
}

test("the ask button covers no other control", async ({ page }) => {
  await oneBook(page);
  await page.goto("/library/doc-1");
  await expect(page.getByRole("button", { name: "සිංහල පොත කියවන්න." })).toBeVisible();
  const covered = await page.evaluate(() => {
    const ask = document.querySelector(".assistant-fab")?.getBoundingClientRect();
    if (!ask) return ["no ask button"];
    return [...document.querySelectorAll("a[href], button, select, input")]
      .filter((element) => !element.classList.contains("assistant-fab"))
      .filter((element) => {
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) return false;
        return box.left < ask.right && box.right > ask.left && box.top < ask.bottom && box.bottom > ask.top;
      })
      .map((element) => element.textContent.trim());
  });
  expect(covered).toEqual([]);
});
