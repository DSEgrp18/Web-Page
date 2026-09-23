import { describe, expect, it, vi } from "vitest";

import { passThrough } from "../src/lib/passThrough";

const ENV = { READER_API_URL: "http://api.internal:8000/" };

/** A fake API that records what it was sent and answers as told. */
function fakeApi(answer: () => Response = () => Response.json({ ok: true })) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return answer();
  }) as unknown as typeof fetch;
  return { calls, fetchImpl };
}

function sent(calls: { init: RequestInit }[]): Headers {
  return new Headers(calls[0]!.init.headers);
}

describe("the pass-through", () => {
  it("forwards the path and query to the configured API", async () => {
    const api = fakeApi();
    await passThrough(
      new Request("https://swara.test/api/documents/doc-1/pages/3?x=1"),
      ["documents", "doc-1", "pages", "3"],
      { env: ENV, fetchImpl: api.fetchImpl },
    );

    expect(api.calls[0]!.url).toBe("http://api.internal:8000/documents/doc-1/pages/3?x=1");
  });

  it("cannot be steered off the API by a crafted path", async () => {
    const api = fakeApi();
    await passThrough(new Request("https://swara.test/api/x"), ["..", "@evil.test", "a b"], {
      env: ENV,
      fetchImpl: api.fetchImpl,
    });

    const url = new URL(api.calls[0]!.url);
    expect(url.host).toBe("api.internal:8000");
    expect(api.calls[0]!.url).toContain("%40evil.test");
  });

  it("says so when the API address is not configured", async () => {
    const response = await passThrough(
      new Request("https://swara.test/api/documents"),
      ["documents"],
      {
        env: {},
        fetchImpl: fakeApi().fetchImpl,
      },
    );

    expect(response.status).toBe(503);
  });

  it("drops every credential but the cookie", async () => {
    const api = fakeApi();
    await passThrough(
      new Request("https://swara.test/api/documents", {
        headers: {
          cookie: "__Host-swara_session=abc",
          "x-csrf-token": "t",
          "x-reader-user": "someone-else",
          authorization: "Bearer stolen",
          "x-session-transport": "bearer",
          "sec-fetch-site": "same-origin",
        },
      }),
      ["documents"],
      { env: ENV, fetchImpl: api.fetchImpl },
    );

    const headers = sent(api.calls);
    expect(headers.get("cookie")).toBe("__Host-swara_session=abc");
    expect(headers.get("x-csrf-token")).toBe("t");
    expect(headers.get("sec-fetch-site")).toBe("same-origin");
    expect(headers.get("x-reader-user")).toBeNull();
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-session-transport")).toBeNull();
  });

  it("passes the reader's address on only from a proxy it trusts", async () => {
    const request = () =>
      new Request("https://swara.test/api/auth/login", {
        method: "POST",
        headers: { "x-forwarded-for": "6.6.6.6, 203.0.113.9" },
        body: "{}",
      });
    const untrusted = fakeApi();
    const trusted = fakeApi();

    await passThrough(request(), ["auth", "login"], { env: ENV, fetchImpl: untrusted.fetchImpl });
    await passThrough(request(), ["auth", "login"], {
      env: { ...ENV, READER_BEHIND_PROXY: "1" },
      fetchImpl: trusted.fetchImpl,
    });

    // Without a proxy, the header is whatever the client typed.
    expect(sent(untrusted.calls).get("x-forwarded-for")).toBeNull();
    // With one, only the address it appended; the rest came from the client.
    expect(sent(trusted.calls).get("x-forwarded-for")).toBe("203.0.113.9");
  });

  it("returns every cookie the API set, separately", async () => {
    const api = fakeApi(() => {
      const headers = new Headers({ "content-type": "application/json" });
      headers.append("set-cookie", "a=1; Expires=Wed, 01 Jan 2031 00:00:00 GMT; Path=/");
      headers.append("set-cookie", "b=2; Path=/");
      return new Response("{}", { status: 201, headers });
    });

    const response = await passThrough(
      new Request("https://swara.test/api/auth/register", { method: "POST", body: "{}" }),
      ["auth", "register"],
      { env: ENV, fetchImpl: api.fetchImpl },
    );

    expect(response.status).toBe(201);
    expect(response.headers.getSetCookie()).toEqual([
      "a=1; Expires=Wed, 01 Jan 2031 00:00:00 GMT; Path=/",
      "b=2; Path=/",
    ]);
  });

  it("keeps what audio and PDFs need, and nothing else", async () => {
    const api = fakeApi(
      () =>
        new Response("bytes", {
          status: 206,
          headers: {
            "content-type": "application/pdf",
            "content-range": "bytes 0-4/100",
            "accept-ranges": "bytes",
            "x-reader-real-model": "false",
            "retry-after": "30",
            server: "uvicorn",
            "x-internal": "secret",
          },
        }),
    );

    const response = await passThrough(
      new Request("https://swara.test/api/documents/d/file", { headers: { range: "bytes=0-4" } }),
      ["documents", "d", "file"],
      { env: ENV, fetchImpl: api.fetchImpl },
    );

    expect(sent(api.calls).get("range")).toBe("bytes=0-4");
    expect(response.status).toBe(206);
    expect(response.headers.get("content-range")).toBe("bytes 0-4/100");
    expect(response.headers.get("x-reader-real-model")).toBe("false");
    expect(response.headers.get("retry-after")).toBe("30");
    expect(response.headers.get("server")).toBeNull();
    expect(response.headers.get("x-internal")).toBeNull();
    expect(await response.text()).toBe("bytes");
  });

  it("streams a body rather than buffering it", async () => {
    const api = fakeApi();
    const request = new Request("https://swara.test/api/documents", {
      method: "POST",
      body: "a large upload",
      headers: { "content-type": "application/octet-stream" },
    });

    await passThrough(request, ["documents"], { env: ENV, fetchImpl: api.fetchImpl });

    const init = api.calls[0]!.init as RequestInit & { duplex?: string };
    expect(init.body).toBeInstanceOf(ReadableStream);
    expect(init.duplex).toBe("half");
  });

  it("sends no body for a read", async () => {
    const api = fakeApi();
    await passThrough(new Request("https://swara.test/api/documents"), ["documents"], {
      env: ENV,
      fetchImpl: api.fetchImpl,
    });

    expect(api.calls[0]!.init.body).toBeUndefined();
  });

  it("answers 502 when the API cannot be reached", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;

    const response = await passThrough(
      new Request("https://swara.test/api/documents"),
      ["documents"],
      {
        env: ENV,
        fetchImpl,
      },
    );

    expect(response.status).toBe(502);
    errors.mockRestore();
  });

  it("gives up after its timeout with 504", async () => {
    const fetchImpl = vi.fn(
      (_url: unknown, init?: RequestInit) =>
        new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("", "AbortError")));
        }),
    ) as unknown as typeof fetch;

    const response = await passThrough(
      new Request("https://swara.test/api/documents"),
      ["documents"],
      {
        env: ENV,
        fetchImpl,
        timeoutMs: 20,
      },
    );

    expect(response.status).toBe(504);
  });
});
