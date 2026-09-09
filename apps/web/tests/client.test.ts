import { describe, expect, it, vi } from "vitest";

import { ApiError, ReaderApi, type FailureKind } from "../src/lib/client";
import { FakeServer, OWNER, readablePage } from "./fakeApi";

function serverWithBook() {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["පළමු වාක්‍යය."])],
      },
    ],
  });
}

function apiFor(server: FakeServer, owner = OWNER) {
  return new ReaderApi(owner, { baseUrl: "http://api.test", fetchImpl: server.fetch });
}

describe("identity", () => {
  it("sends the reader's identity on every request", async () => {
    const server = serverWithBook();
    await apiFor(server).listDocuments();
    expect(server.calls[0]?.owner).toBe(OWNER);
  });

  it("refuses to make a request at all with no identity", async () => {
    const server = serverWithBook();
    await expect(apiFor(server, "").listDocuments()).rejects.toMatchObject({ kind: "identity" });
    // Not "the server said no" — the request never happened.
    expect(server.calls).toHaveLength(0);
  });
});

describe("failures", () => {
  const cases: [number, FailureKind][] = [
    [404, "not_found"],
    [409, "not_ready"],
    [422, "unspeakable"],
    [413, "rejected"],
    [503, "identity"],
    [500, "server"],
  ];

  for (const [status, kind] of cases) {
    it(`turns ${status} into ${kind}`, async () => {
      const fetchImpl = vi.fn(
        async () => new Response(JSON.stringify({ detail: "no" }), { status }),
      ) as unknown as typeof fetch;
      const api = new ReaderApi(OWNER, { baseUrl: "http://api.test", fetchImpl });
      await expect(api.listDocuments()).rejects.toMatchObject({ kind });
    });
  }

  it("reports a dead server as offline rather than as an error page", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const api = new ReaderApi(OWNER, { baseUrl: "http://api.test", fetchImpl });
    const error = await api.listDocuments().catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe("offline");
  });

  it("does not confuse a missing document with someone else's", async () => {
    // The API answers 404 for both, deliberately. The client must not invent a
    // distinction the server refused to make.
    const server = serverWithBook();
    await expect(apiFor(server).getDocument("someone-elses")).rejects.toMatchObject({
      kind: "not_found",
      status: 404,
    });
  });
});

describe("audio", () => {
  it("carries whether a real model produced it", async () => {
    const server = serverWithBook();
    server.realModel = true;
    const clip = await apiFor(server).getAudio("doc-1", "0000-s0");
    expect(clip.realModel).toBe(true);
    expect(clip.blob.size).toBeGreaterThan(0);
  });

  it("treats a placeholder as a placeholder", async () => {
    const server = serverWithBook();
    server.realModel = false;
    expect((await apiFor(server).getAudio("doc-1", "0000-s0")).realModel).toBe(false);
  });

  it("treats a missing header as not real", async () => {
    // Unknown must never read as "this is speech". A header the server forgot
    // to send, or a proxy that stripped it, must fail towards honesty.
    const fetchImpl = vi.fn(
      async () => new Response(new Uint8Array([1, 2, 3]), { status: 200 }),
    ) as unknown as typeof fetch;
    const api = new ReaderApi(OWNER, { baseUrl: "http://api.test", fetchImpl });
    expect((await api.getAudio("doc-1", "0000-s0")).realModel).toBe(false);
  });
});

describe("progress", () => {
  it("saves and reads back a position", async () => {
    const server = serverWithBook();
    const api = apiFor(server);
    await api.saveProgress("doc-1", "0000-s0", 4.5);
    const read = await api.getProgress("doc-1");
    expect(read).toMatchObject({ segment_id: "0000-s0", offset_seconds: 4.5, stale: false });
  });

  it("reports no saved position as not found rather than as an empty one", async () => {
    const server = serverWithBook();
    await expect(apiFor(server).getProgress("doc-1")).rejects.toMatchObject({ kind: "not_found" });
  });
});
