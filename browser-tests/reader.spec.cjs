const { test, expect } = require("@playwright/test");
const { apiUrl, mockApi } = require("./session.cjs");

test("reader shows the current sentence as words without autoplay", async ({ page }) => {
  let audioRequests = 0;
  await mockApi(page, async (route) => {
    const request = route.request();
    const url = apiUrl(request);
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

  await page.goto("/library/doc-1");
  const toggle = page.getByRole("button", { name: "වචන බලන්න" });
  await expect(toggle).toBeEnabled();
  await toggle.click();
  const words = page.getByRole("region", { name: "වාක්‍යයේ වචන" });
  await expect(words.locator("li")).toHaveText(["සිංහල", "පොත", "කියවන්න"]);
  await expect(page.getByRole("button", { name: "වචන සඟවන්න" })).toHaveAttribute("aria-expanded", "true");
  expect(audioRequests).toBe(0);
  // The tab is named after the book once it has loaded (WCAG 2.4.2).
  await expect(page).toHaveTitle("පොත.pdf — ස්වර");
});

test("library uploads PDF and DOCX files together", async ({ page }) => {
  let uploads = 0;
  const documents = [];
  await mockApi(page, async (route) => {
    const request = route.request();
    const url = apiUrl(request);
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
    if (request.method() === "GET" && url.pathname === "/documents") {
      await route.fulfill({ status: 200, headers, body: JSON.stringify(documents) });
      return;
    }
    if (request.method() === "POST" && url.pathname === "/documents") {
      uploads += 1;
      const filename = uploads === 1 ? "පොත.pdf" : "සටහන්.docx";
      const mediaType = uploads === 1
        ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
      const document = {
        document_id: `doc-${uploads}`, filename, media_type: mediaType, title: null,
        size_bytes: 100, created_at: "2026-09-21T00:00:00Z", version: null,
        page_count: 0, segment_count: 0, reading: null, notes: [], chapters: null,
        job: { job_id: `job-${uploads}`, kind: "prepare", state: "queued", stage: "queued", detail: null, updated_at: "2026-09-21T00:00:00Z" },
      };
      documents.push(document);
      await route.fulfill({
        status: 202,
        headers,
        body: JSON.stringify(document),
      });
      return;
    }
    await route.fulfill({ status: 404, headers, body: JSON.stringify({ detail: "not found" }) });
  });

  await page.goto("/library");
  // A real browser, not the metadata object: the root page shares the root
  // layout's segment, where its title template does not apply, and a unit
  // test that reads the metadata cannot see that.
  await expect(page).toHaveTitle("මගේ පොත් — ස්වර");
  await page.getByRole("button", { name: /පොතක් එක් කරන්න/ }).click();
  await page.getByLabel("ගොනුවක් තෝරන්න").setInputFiles([
    { name: "පොත.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-") },
    { name: "සටහන්.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("docx") },
  ]);
  await page.getByRole("button", { name: "එක් කරන්න", exact: true }).click();

  await expect(page.getByRole("heading", { name: "පොත.pdf" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "සටහන්.docx" })).toBeVisible();
  await expect(page.getByRole("button", { name: "පොතක් එක් කරන්න", exact: true })).toBeFocused();
  expect(uploads).toBe(2);
});

test("an old saved link reaches the same sentence under /library", async ({ page }) => {
  await mockApi(page, async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not found" } });
  });

  const response = await page.goto("/documents/doc-1?segment=0000-s1");

  // A permanent redirect, with the sentence kept.
  expect(response.request().redirectedFrom()?.url()).toContain("/documents/doc-1?segment=0000-s1");
  expect(new URL(page.url()).pathname).toBe("/library/doc-1");
  expect(new URL(page.url()).searchParams.get("segment")).toBe("0000-s1");
});
