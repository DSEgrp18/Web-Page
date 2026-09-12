/**
 * A stand-in for the reader API, at the HTTP boundary.
 *
 * The tests could mock `ReaderApi` and be shorter. They mock `fetch` instead so
 * that the client — its headers, its status-to-failure mapping, its reading of
 * `X-Reader-Real-Model` — is under test rather than replaced by the test.
 *
 * The shapes here are copied from `services/api/src/sinhala_reader/schemas.py`.
 * If they drift, `npm run verify:contract` says so against a running server;
 * these tests cannot, and do not claim to.
 */

import type { Bookmark, DocumentDetail, Page, Progress, Segment } from "../src/lib/types";

export const OWNER = "reader-one";

export interface FakeBook {
  document_id: string;
  filename: string;
  /** Null while it is still being prepared. */
  version: string | null;
  pages: Page[];
  notes?: string[];
}

export interface FakeServerOptions {
  books?: FakeBook[];
  /** False makes every audio response a placeholder tone, as the API does today. */
  realModel?: boolean;
  progress?: Progress | null;
  bookmarks?: Bookmark[];
  /** Number of `GET /documents` calls an upload stays unprepared for. */
  preparationPolls?: number;
}

export interface RecordedCall {
  method: string;
  path: string;
  owner: string | null;
  body?: unknown;
}

/** Sixteen bytes of silent 8 kHz mono WAV — enough to be a real audio blob. */
function wavBytes(): Uint8Array<ArrayBuffer> {
  const header = new Uint8Array(44);
  const view = new DataView(header.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36, true);
  ascii(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, 0, true);
  return header;
}

export function segment(
  pageIndex: number,
  index: number,
  text: string,
  pageLabel: string | null = null,
): Segment {
  return {
    segment_id: `${String(pageIndex).padStart(4, "0")}-s${index}`,
    index,
    page_index: pageIndex,
    page_label: pageLabel,
    display_text: text,
    spoken_text: text,
    boxes: [],
  };
}

export function readablePage(pageIndex: number, texts: string[], pageLabel = "12"): Page {
  return {
    page_index: pageIndex,
    page_label: pageLabel,
    kind: "text",
    quality: "accepted",
    notes: [],
    segments: texts.map((text, index) => segment(pageIndex, index, text, pageLabel)),
  };
}

export class FakeServer {
  readonly calls: RecordedCall[] = [];
  books: FakeBook[];
  progress: Progress | null;
  bookmarks: Bookmark[];
  realModel: boolean;
  private pollsLeft: number;
  private counter = 0;

  constructor(options: FakeServerOptions = {}) {
    this.books = options.books ?? [];
    this.progress = options.progress ?? null;
    this.bookmarks = options.bookmarks ?? [];
    this.realModel = options.realModel ?? false;
    this.pollsLeft = options.preparationPolls ?? 0;
  }

  get fetch(): typeof fetch {
    return this.handle.bind(this) as unknown as typeof fetch;
  }

  /** Every call the interface made, so a test can assert what it did *not* do. */
  callsTo(method: string, pattern: RegExp): RecordedCall[] {
    return this.calls.filter((call) => call.method === method && pattern.test(call.path));
  }

  private async handle(url: string, init: RequestInit = {}): Promise<Response> {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    const owner = headers.get("X-Reader-User");
    this.calls.push({ method, path, owner, body: init.body });

    // The real API refuses to answer anything without an identity.
    if (!owner) return this.json({ detail: "unauthenticated" }, 503);

    if (method === "GET" && path === "/documents") return this.listDocuments();
    if (method === "POST" && path === "/documents") return this.upload(init);

    const audio = /^\/documents\/([^/]+)\/segments\/([^/]+)\/audio$/.exec(path);
    if (method === "GET" && audio) return this.audio(audio[1]!, audio[2]!);

    const seg = /^\/documents\/([^/]+)\/segments\/([^/]+)$/.exec(path);
    if (method === "GET" && seg) return this.segment(seg[1]!, seg[2]!);

    const page = /^\/documents\/([^/]+)\/pages\/(-?\d+)$/.exec(path);
    if (method === "GET" && page) return this.page(page[1]!, Number(page[2]));

    const progress = /^\/documents\/([^/]+)\/progress$/.exec(path);
    if (progress) {
      if (method === "PUT") return this.saveProgress(progress[1]!, init);
      if (method === "GET")
        return this.progress ? this.json(this.progress) : this.json({ detail: "none" }, 404);
    }

    const bookmark = /^\/documents\/([^/]+)\/bookmarks\/([^/]+)$/.exec(path);
    if (method === "DELETE" && bookmark) return this.deleteBookmark(bookmark[1]!, bookmark[2]!);

    const bookmarks = /^\/documents\/([^/]+)\/bookmarks$/.exec(path);
    if (bookmarks) {
      if (method === "POST") return this.addBookmark(bookmarks[1]!, init);
      if (method === "GET") return this.listBookmarks(bookmarks[1]!);
    }

    const detail = /^\/documents\/([^/]+)$/.exec(path);
    if (detail) {
      if (method === "GET") {
        const book = this.book(detail[1]!);
        return book ? this.json(this.summarise(book)) : this.notFound();
      }
      if (method === "DELETE") {
        this.books = this.books.filter((candidate) => candidate.document_id !== detail[1]);
        return new Response(null, { status: 204 });
      }
    }

    return this.notFound();
  }

  private book(id: string): FakeBook | undefined {
    return this.books.find((candidate) => candidate.document_id === id);
  }

  private summarise(book: FakeBook): DocumentDetail {
    const segments = book.pages.reduce((total, page) => total + page.segments.length, 0);
    return {
      document_id: book.document_id,
      filename: book.filename,
      size_bytes: 1024,
      created_at: "2026-09-09T00:00:00Z",
      version: book.version,
      page_count: book.pages.length,
      segment_count: segments,
      notes: book.notes ?? [],
      job: {
        job_id: `job-${book.document_id}`,
        kind: "prepare",
        state: book.version ? "succeeded" : "running",
        stage: "extract",
        detail: null,
        updated_at: "2026-09-09T00:00:00Z",
      },
    };
  }

  private listDocuments(): Response {
    const listed = this.books.map((book) => {
      const summary = this.summarise(book);
      if (this.pollsLeft > 0) {
        this.pollsLeft -= 1;
        return { ...summary, version: null };
      }
      return summary;
    });
    return this.json(listed);
  }

  private async upload(init: RequestInit): Promise<Response> {
    const body = init.body as FormData;
    const file = body.get("file") as File | null;
    this.counter += 1;
    const book: FakeBook = {
      document_id: `doc-${this.counter}`,
      filename: file?.name ?? "book.pdf",
      version: "v1",
      pages: [readablePage(0, ["පළමු වාක්‍යය.", "දෙවන වාක්‍යය."])],
    };
    this.books.push(book);
    return this.json(this.summarise(book), 202);
  }

  private page(id: string, index: number): Response {
    const book = this.book(id);
    if (!book) return this.notFound();
    if (!book.version) return this.json({ detail: "not ready" }, 409);
    const found = book.pages.find((candidate) => candidate.page_index === index);
    return found ? this.json(found) : this.notFound();
  }

  private segment(id: string, segmentId: string): Response {
    const book = this.book(id);
    if (!book) return this.notFound();
    for (const page of book.pages) {
      const found = page.segments.find((candidate) => candidate.segment_id === segmentId);
      if (found) return this.json(found);
    }
    return this.notFound();
  }

  private audio(id: string, segmentId: string): Response {
    const book = this.book(id);
    if (!book) return this.notFound();
    const exists = book.pages.some((page) =>
      page.segments.some((candidate) => candidate.segment_id === segmentId),
    );
    if (!exists) return this.notFound();
    // The buffer, not the view: undici's Response and jsdom's Blob are
    // different implementations and do not accept each other.
    return new Response(wavBytes().buffer, {
      status: 200,
      headers: {
        "Content-Type": "audio/wav",
        "X-Reader-Real-Model": this.realModel ? "true" : "false",
      },
    });
  }

  private async saveProgress(id: string, init: RequestInit): Promise<Response> {
    const book = this.book(id);
    if (!book) return this.notFound();
    const body = JSON.parse(String(init.body)) as { segment_id: string; offset_seconds: number };
    this.progress = {
      document_id: id,
      segment_id: body.segment_id,
      offset_seconds: body.offset_seconds,
      document_version: book.version ?? "v1",
      updated_at: "2026-09-09T00:00:00Z",
      stale: false,
    };
    return this.json(this.progress);
  }

  private listBookmarks(id: string): Response {
    if (!this.book(id)) return this.notFound();
    return this.json(this.bookmarks.filter((bookmark) => bookmark.document_id === id));
  }

  private async addBookmark(id: string, init: RequestInit): Promise<Response> {
    const book = this.book(id);
    if (!book || !book.version) return this.notFound();
    const body = JSON.parse(String(init.body)) as { segment_id: string; note?: string };
    const segment = book.pages
      .flatMap((page) => page.segments)
      .find((item) => item.segment_id === body.segment_id);
    if (!segment) return this.notFound();

    const existing = this.bookmarks.find(
      (bookmark) => bookmark.document_id === id && bookmark.segment_id === body.segment_id,
    );
    const bookmark: Bookmark = {
      bookmark_id: existing?.bookmark_id ?? `bmk-${this.counter + this.bookmarks.length + 1}`,
      document_id: id,
      segment_id: segment.segment_id,
      note: body.note?.trim() || null,
      created_at: existing?.created_at ?? "2026-09-09T00:00:00Z",
      document_version: book.version,
      stale: false,
      segment_found: true,
      page_index: segment.page_index,
      page_label: segment.page_label,
      display_text: segment.display_text,
    };
    this.bookmarks = existing
      ? this.bookmarks.map((candidate) =>
          candidate.bookmark_id === bookmark.bookmark_id ? bookmark : candidate,
        )
      : [...this.bookmarks, bookmark];
    return this.json(bookmark, existing ? 200 : 201);
  }

  private deleteBookmark(id: string, bookmarkId: string): Response {
    const exists = this.bookmarks.some(
      (bookmark) => bookmark.document_id === id && bookmark.bookmark_id === bookmarkId,
    );
    if (!exists) return this.notFound();
    this.bookmarks = this.bookmarks.filter((bookmark) => bookmark.bookmark_id !== bookmarkId);
    return new Response(null, { status: 204 });
  }

  private notFound(): Response {
    return this.json({ detail: "No such document." }, 404);
  }

  private json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }
}
