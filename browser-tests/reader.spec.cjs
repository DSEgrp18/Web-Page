const { test, expect } = require("@playwright/test");

test("reader shows the current sentence as words without autoplay", async ({ page }) => {
  let audioRequests = 0;
  await page.addInitScript(() => localStorage.setItem("sinhala-reader.identity", "browser-tester"));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/audio")) audioRequests += 1;
    const headers = {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "*",
      "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
      "content-type": "application/json",
    };
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    const detail = {
      document_id: "doc-1", filename: "පොත.pdf", title: null, size_bytes: 1024,
      created_at: "2026-09-20T00:00:00Z", version: "v1", page_count: 1, segment_count: 2,
      reading: null, notes: [], chapters: [],
      job: { job_id: "job-1", kind: "prepare", state: "succeeded", stage: "extract", detail: null, updated_at: "2026-09-20T00:00:00Z" },
    };
    const segment = (index, text) => ({
      segment_id: `0000-s${index}`, index, page_index: 0, page_label: "1",
      display_text: text, spoken_text: text, boxes: [], role: "unknown", level: null,
    });
    const body = url.pathname === "/documents/doc-1" ? detail
      : url.pathname === "/documents/doc-1/pages/0" ? {
        page_index: 0, page_label: "1", kind: "text", quality: "accepted", notes: [],
        segments: [segment(0, "සිංහල පොත කියවන්න."), segment(1, "ඊළඟ වාක්‍යය මෙහි ඇත.")],
      } : null;
    await route.fulfill({ status: body ? 200 : 404, headers, body: JSON.stringify(body ?? { detail: "not found" }) });
  });

  await page.goto("/documents/doc-1");
  const toggle = page.getByRole("button", { name: "වචන බලන්න" });
  await expect(toggle).toBeEnabled();
  await toggle.click();
  const words = page.getByRole("region", { name: "වාක්‍යයේ වචන" });
  await expect(words.locator("li")).toHaveText(["සිංහල", "පොත", "කියවන්න"]);
  await expect(page.getByRole("button", { name: "වචන සඟවන්න" })).toHaveAttribute("aria-expanded", "true");
  expect(audioRequests).toBe(0);
});
