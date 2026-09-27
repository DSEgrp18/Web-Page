import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { OfflineLibrary } from "../src/components/OfflineLibrary";
import { SaveOffline } from "../src/components/SaveOffline";
import { DOWNLOADS, audioUrl, listSaved, removeSaved, saveChapter } from "../src/lib/offline";
import { strings } from "../src/lib/strings";
import type { OfflineManifest } from "../src/lib/types";
import { FakeCacheStorage } from "./fakeCaches";
import { FakeServer, readablePage } from "./fakeApi";
import { noticeText, politeText, renderApp } from "./render";

const MANIFEST: OfflineManifest = {
  document_id: "doc-1",
  version: "v1",
  title: "ඉතිහාසය",
  chapter: "පළමු පරිච්ඡේදය",
  first_page: 0,
  last_page: 0,
  clips: [
    { segment_id: "0000-s0", page_index: 0, page_label: "1", text: "පළමු වාක්‍යය.", ready: true },
    { segment_id: "0000-s1", page_index: 0, page_label: "1", text: "දෙවන වාක්‍යය.", ready: false },
  ],
  ready: 1,
  total: 2,
  truncated: false,
};

/** Audio for any clip, and a tiny offline page naming one static file. */
async function network(input: RequestInfo | URL): Promise<Response> {
  const url = String(input);
  if (url.endsWith("/audio")) return new Response("OggS-audio", { status: 200 });
  if (url === "/offline") {
    return new Response('<script src="/_next/static/chunks/app.js"></script>', { status: 200 });
  }
  return new Response("console.log(1)", { status: 200 });
}

let storage: FakeCacheStorage;

beforeEach(() => {
  storage = new FakeCacheStorage();
  vi.stubGlobal("caches", storage);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("saving a chapter", () => {
  it("keeps the clips that have audio, and marks the rest as missing", async () => {
    const saved = await saveChapter(MANIFEST, () => {}, network as typeof fetch);

    expect(saved.clips.map((c) => c.url)).toEqual([audioUrl("doc-1", "0000-s0"), null]);
    expect(saved.bytes).toBe(10);
    expect((await listSaved()).map((e) => e.key)).toEqual(["doc-1:0"]);
    const shell = await storage.open("swara-shell-v1");
    expect(await shell.match("/offline")).toBeTruthy();
    expect(await shell.match("/_next/static/chunks/app.js")).toBeTruthy();
  });

  it("removes its audio with it", async () => {
    const saved = await saveChapter(MANIFEST, () => {}, network as typeof fetch);

    await removeSaved(saved);

    expect(await listSaved()).toEqual([]);
    const downloads = await storage.open(DOWNLOADS);
    expect(await downloads.keys()).toEqual([]);
  });
});

describe("the saved chapters page", () => {
  it("lists each chapter with its size and what has no audio", async () => {
    await saveChapter(MANIFEST, () => {}, network as typeof fetch);
    const { container } = renderApp(<OfflineLibrary />, new FakeServer({ books: [] }));

    expect(await screen.findByRole("heading", { name: "ඉතිහාසය — පළමු පරිච්ඡේදය" })).toBeTruthy();
    expect(screen.getByText(new RegExp(strings.offlineMissing(1)))).toBeTruthy();
    expect((await axe.run(container)).violations.map((v) => v.id)).toEqual([]);
  });

  it("removes a chapter and says so", async () => {
    const user = userEvent.setup();
    await saveChapter(MANIFEST, () => {}, network as typeof fetch);
    renderApp(<OfflineLibrary />, new FakeServer({ books: [] }));

    await user.click(await screen.findByRole("button", { name: /ඉවත් කරන්න/ }));

    expect(await screen.findByText(strings.offlineNothing)).toBeTruthy();
    expect(politeText()).toContain(strings.offlineRemoved("පළමු පරිච්ඡේදය"));
  });

  it("opens a player that marks sentences with no audio and plays nothing yet", async () => {
    const user = userEvent.setup();
    await saveChapter(MANIFEST, () => {}, network as typeof fetch);
    renderApp(<OfflineLibrary />, new FakeServer({ books: [] }));

    await user.click(await screen.findByRole("button", { name: /අසන්න/ }));

    expect(screen.getByRole("button", { name: "පළමු වාක්‍යය." })).toBeTruthy();
    expect(screen.getByText(new RegExp(strings.offlineNoAudio))).toBeTruthy();
    expect(screen.getByRole("button", { name: strings.play })).toBeTruthy();
  });
});

describe("the save button in the reader", () => {
  function server(manifest: OfflineManifest): FakeServer {
    const fake = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["පළමු වාක්‍යය.", "දෙවන වාක්‍යය."])],
        },
      ],
    });
    fake.offline = manifest;
    return fake;
  }

  it("saves what has audio and says how much", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", network);
    renderApp(<SaveOffline documentId="doc-1" page={0} />, server(MANIFEST));

    await user.click(screen.getByRole("button", { name: strings.offlineSave }));

    await waitFor(() => expect(politeText()).toContain(strings.offlineSaved(1, 2)));
    expect((await listSaved()).length).toBe(1);
  });

  it("says so when nothing in the chapter has audio yet", async () => {
    const user = userEvent.setup();
    renderApp(
      <SaveOffline documentId="doc-1" page={0} />,
      server({ ...MANIFEST, clips: MANIFEST.clips.map((c) => ({ ...c, ready: false })), ready: 0 }),
    );

    await user.click(screen.getByRole("button", { name: strings.offlineSave }));

    await waitFor(() => expect(noticeText()).toContain(strings.offlineNoneVoiced));
    expect(await listSaved()).toEqual([]);
  });
});

describe("signing out", () => {
  it("deletes every saved chapter, since phones are shared", async () => {
    const user = userEvent.setup();
    await saveChapter(MANIFEST, () => {}, network as typeof fetch);
    renderApp(
      <AppFrame>
        <p>—</p>
      </AppFrame>,
      new FakeServer(),
    );

    await user.click(await screen.findByRole("button", { name: strings.signOut }));

    await waitFor(async () => expect(await storage.keys()).toEqual([]));
    expect(await listSaved()).toEqual([]);
  });
});
