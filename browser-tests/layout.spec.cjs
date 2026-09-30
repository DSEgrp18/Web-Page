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

test("no page scrolls sideways at any width from 320 to 1400 px", async ({ page }) => {
  // The masthead's one row needs about 60em; between 780 and 920 px it pushed
  // every signed-in page sideways, which a check at 320 px alone never saw.
  await oneBook(page);
  const over = [];
  for (const path of ["/library", "/library/doc-1", "/"]) {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    await page.waitForLoadState("networkidle");
    for (let width = 320; width <= 1400; width += 20) {
      await page.setViewportSize({ width, height: 800 });
      const by = await sideways(page);
      if (by > 0) over.push(`${path} at ${width}: ${by} px`);
    }
  }
  expect(over).toEqual([]);
});

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

test.describe("on a phone", () => {
  test.use({ viewport: { width: 360, height: 780 } });

  test("the book's text has room, and no sentence sits under the player", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    // The masthead there is static and three times the height the old
    // full-height layout subtracted, which left the text 130 px.
    const panel = page.locator("#panel-reading");
    await expect(page.getByRole("button", { name: "සිංහල පොත කියවන්න." })).toBeVisible();
    expect((await panel.boundingBox())?.height).toBeGreaterThan(200);

    for (const name of ["සිංහල පොත කියවන්න.", "ඊළඟ වාක්‍යය මෙහි ඇත."]) {
      const sentence = page.getByRole("button", { name });
      await sentence.focus();
      // What a tap at the middle of the focused sentence would hit: the
      // sentence, not the player pinned over the page.
      const hit = await sentence.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return element.contains(top);
      });
      expect(hit, name).toBe(true);
    }
  });

  test("the player stays on screen, and the ask button covers none of it", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: "සිංහල පොත කියවන්න." })).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));

    const player = page.getByRole("group", { name: /./ }).filter({ has: page.locator(".player-play") });
    const box = await player.boundingBox();
    expect(box && box.y + box.height).toBeLessThanOrEqual(780);

    const covered = await page.evaluate(() => {
      const ask = document.querySelector(".assistant-fab")?.getBoundingClientRect();
      if (!ask) return ["no ask button"];
      return [...document.querySelectorAll(".player button, .player select")]
        .filter((element) => {
          const b = element.getBoundingClientRect();
          return b.left < ask.right && b.right > ask.left && b.top < ask.bottom && b.bottom > ask.top;
        })
        .map((element) => element.textContent.trim() || element.getAttribute("aria-label"));
    });
    expect(covered).toEqual([]);
  });

  test("the ask button still has a name when only its icon shows", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    // Its label is hidden from sight at this width; hidden with display:none,
    // it was hidden from screen readers too, and the button had no name.
    await expect(page.getByRole("button", { name: "පොත ගැන අසන්න" })).toBeVisible();
  });

  test("a tab shows its panel even after 'expand' collapsed it", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    const sentence = page.getByRole("button", { name: "සිංහල පොත කියවන්න." });
    await expect(sentence).toBeVisible();
    // "Expand the original" hides the reading panel on a wide screen; here the
    // tabs decide, and choosing the reading tab showed an empty screen.
    await page.getByRole("button", { name: "මුල් පිටුව විශාල කරන්න" }).click();
    await page.getByRole("tab", { name: "කියවීම" }).click();
    await expect(sentence).toBeVisible();
  });

  test("every library filter is on screen", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library");
    const filters = page.locator(".shelf-filters .segment");
    await expect(filters.first()).toBeVisible();
    for (const filter of await filters.all()) {
      const box = await filter.boundingBox();
      expect(box && box.x).toBeGreaterThanOrEqual(0);
      expect(box && box.x + box.width).toBeLessThanOrEqual(360);
    }
  });
});

test.describe("the split and the Ask panel, on a wide screen", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  const FIRST = "සිංහල පොත කියවන්න.";

  test("the Ask panel sits beside the book, not over it", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    await page.getByRole("button", { name: "පොත ගැන අසන්න" }).click();
    const drawer = page.getByRole("complementary", { name: "පොත ගැන අසන්න" });
    await expect(drawer).toBeVisible();

    const aside = await drawer.boundingBox();
    const body = await page.locator(".workspace-body").boundingBox();
    // The book's area ends where the panel begins; nothing of it is under it.
    expect(body.x + body.width).toBeLessThanOrEqual(aside.x + 1);
    const hit = await page.getByRole("button", { name: FIRST }).evaluate((element) => {
      const box = element.getBoundingClientRect();
      return element.contains(document.elementFromPoint(box.right - 4, box.top + box.height / 2));
    });
    expect(hit).toBe(true);
  });

  test("its width moves with the keyboard, pushes the book, and is kept", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    await page.getByRole("button", { name: "පොත ගැන අසන්න" }).click();
    const drawer = page.getByRole("complementary", { name: "පොත ගැන අසන්න" });
    const before = (await drawer.boundingBox()).width;

    await page.getByRole("separator", { name: "ප්‍රශ්න පැනලයේ පළල" }).focus();
    await page.keyboard.press("PageUp");
    await expect.poll(async () => (await drawer.boundingBox()).width).toBeGreaterThan(before + 90);

    await page.reload();
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    await page.getByRole("button", { name: "පොත ගැන අසන්න" }).click();
    expect((await drawer.boundingBox()).width).toBeGreaterThan(before + 90);
  });

  test("when two panels no longer fit beside it, they become tabs", async ({ page }) => {
    await page.setViewportSize({ width: 1000, height: 800 });
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    await expect(page.getByRole("tablist")).toBeHidden();

    await page.getByRole("button", { name: "පොත ගැන අසන්න" }).click();
    await expect(page.getByRole("tablist")).toBeVisible();
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
  });

  test("the divider is easy to take: 48 px to hit, and a drag near the middle lands on it", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    const divider = page.getByRole("separator", { name: "පැනල දෙකේ පළල" });
    const box = await divider.boundingBox();
    const middle = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

    // Twenty pixels either side of a 12 px bar still takes it.
    for (const dx of [-20, 20]) {
      const taken = await page.evaluate(
        ({ x, y }) => document.elementFromPoint(x, y)?.closest(".split-divider") !== null,
        { x: middle.x + dx, y: middle.y },
      );
      expect(taken, `${dx} px`).toBe(true);
    }

    const split = await page.locator(".split").boundingBox();
    await page.mouse.move(middle.x, middle.y);
    await page.mouse.down();
    await page.mouse.move(split.x + split.width * 0.7, middle.y, { steps: 4 });
    await expect(divider).toHaveAttribute("aria-valuenow", "70");
    await page.mouse.move(split.x + split.width * 0.52, middle.y, { steps: 4 });
    await page.mouse.up();
    await expect(divider).toHaveAttribute("aria-valuenow", "50");
  });

  test("a collapsed panel leaves a bar that brings it back", async ({ page }) => {
    await oneBook(page);
    await page.goto("/library/doc-1");
    await expect(page.getByRole("button", { name: FIRST })).toBeVisible();
    await page.getByRole("button", { name: "කියවීම විශාල කරන්න" }).click();
    const bar = page.getByRole("button", { name: "මුල් පිටුව නැවත පෙන්වන්න" });
    await expect(bar).toBeVisible();
    expect((await bar.boundingBox()).width).toBeGreaterThanOrEqual(48);
    await bar.click();
    await expect(page.getByRole("separator", { name: "පැනල දෙකේ පළල" })).toBeFocused();
  });
});

test("the settings panel stays on the screen, and reaches its last control, on a phone", async ({ page }) => {
  // It hung from the gear's end, and on a phone the gear is near the start of
  // the header: the language and theme choices began off the screen.
  await oneBook(page);
  for (const width of [320, 360, 414]) {
    await page.setViewportSize({ width, height: 640 });
    await page.goto("/library");
    await expect(page.getByRole("heading", { name: "පොත.pdf" })).toBeVisible();
    await page.getByRole("button", { name: "කියවීමේ සැකසුම්" }).click();
    const panel = page.locator(".settings-panel");
    const box = await panel.boundingBox();
    expect(box.x, `${width} px`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${width} px`).toBeLessThanOrEqual(width);
    expect(box.y + box.height, `${width} px`).toBeLessThanOrEqual(640);
    // The header does not scroll away, so the panel scrolls inside itself.
    const close = panel.getByRole("button", { name: "වසන්න" });
    await close.scrollIntoViewIfNeeded();
    await expect(close).toBeInViewport();
  }
});
