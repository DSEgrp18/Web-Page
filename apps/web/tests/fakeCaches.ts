/**
 * Cache Storage, in memory, for jsdom (which has none). Just the calls the
 * offline code makes: open, keys, match, put, delete. Keys are resolved
 * against the page, as a browser resolves a relative URL.
 */

function resolve(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost/").href;
}

class FakeCache {
  readonly entries = new Map<string, { body: ArrayBuffer; type: string }>();

  async put(input: RequestInfo | URL, response: Response): Promise<void> {
    const body = await response.arrayBuffer();
    this.entries.set(resolve(input), {
      body,
      type: response.headers.get("Content-Type") ?? "",
    });
  }

  async match(input: RequestInfo | URL): Promise<Response | undefined> {
    const found = this.entries.get(resolve(input));
    return found
      ? new Response(found.body, { headers: { "Content-Type": found.type } })
      : undefined;
  }

  async delete(input: RequestInfo | URL): Promise<boolean> {
    return this.entries.delete(resolve(input));
  }

  async keys(): Promise<Request[]> {
    return [...this.entries.keys()].map((url) => new Request(url));
  }
}

export class FakeCacheStorage {
  readonly named = new Map<string, FakeCache>();

  async open(name: string): Promise<FakeCache> {
    let cache = this.named.get(name);
    if (!cache) {
      cache = new FakeCache();
      this.named.set(name, cache);
    }
    return cache;
  }

  async keys(): Promise<string[]> {
    return [...this.named.keys()];
  }

  async delete(name: string): Promise<boolean> {
    return this.named.delete(name);
  }
}
