/**
 * Talking to the reader API.
 *
 * Two decisions worth knowing about:
 *
 * **Audio is fetched, not pointed at.** An `<audio src>` attribute cannot carry
 * the identity header, and it cannot read `X-Reader-Real-Model`. So audio comes
 * back through `fetch` as a blob, and the "is this actually speech" answer
 * travels with it instead of being looked up separately and possibly forgotten.
 *
 * **Failures become a small set of named kinds.** The interface has to say
 * something out loud for each one, in Sinhala, and it must never guess: the API
 * answers 404 for a document that does not exist *and* for one belonging to
 * someone else, deliberately, so the reader is told "not found" and nothing more.
 */

import type {
  AudioClip,
  AudioManifest,
  Bookmark,
  DocumentDetail,
  DocumentSummary,
  Job,
  Page,
  Progress,
  Readiness,
  Segment,
} from "./types";

export type FailureKind =
  | "offline" // the request never reached a server
  | "identity" // no reader identity, or the server refuses to authenticate
  | "not_found" // no such document, page, or segment — for this reader
  | "not_ready" // the document is still being prepared
  | "rejected" // the upload itself was refused
  | "unspeakable" // this segment has nothing to say
  | "server"; // anything else

export class ApiError extends Error {
  readonly kind: FailureKind;
  readonly status: number;

  constructor(kind: FailureKind, status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

function kindFor(status: number): FailureKind {
  if (status === 401 || status === 403 || status === 503) return "identity";
  if (status === 404) return "not_found";
  if (status === 409) return "not_ready";
  if (status === 422) return "unspeakable";
  if (status === 400 || status === 413 || status === 415) return "rejected";
  return "server";
}

/**
 * Where the API lives. Public because the browser needs it; it is an address,
 * not a secret. Secrets never enter a browser bundle.
 */
export const API_BASE = (process.env.NEXT_PUBLIC_READER_API ?? "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

export const OWNER_HEADER = "X-Reader-User";
export const REAL_MODEL_HEADER = "X-Reader-Real-Model";

export interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export class ReaderApi {
  private readonly baseUrl: string;
  private readonly doFetch: typeof fetch;
  private readonly owner: string;

  constructor(owner: string, options: ClientOptions = {}) {
    this.owner = owner;
    this.baseUrl = (options.baseUrl ?? API_BASE).replace(/\/+$/, "");
    this.doFetch = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    if (!this.owner) {
      throw new ApiError("identity", 0, "No reader identity is set.");
    }
    const headers = new Headers(init.headers);
    headers.set(OWNER_HEADER, this.owner);

    let response: Response;
    try {
      response = await this.doFetch(`${this.baseUrl}${path}`, { ...init, headers });
    } catch (cause) {
      // A network failure and a CORS refusal are indistinguishable here by
      // design of the platform, so the message says what the reader can act on.
      throw new ApiError("offline", 0, String(cause));
    }
    if (!response.ok) {
      throw new ApiError(kindFor(response.status), response.status, await detailOf(response));
    }
    return response;
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    return (await this.request(path, init)).json() as Promise<T>;
  }

  // -- documents ---------------------------------------------------------

  async upload(file: File): Promise<DocumentDetail> {
    const body = new FormData();
    body.append("file", file);
    return this.json<DocumentDetail>("/documents", { method: "POST", body });
  }

  listDocuments(): Promise<DocumentSummary[]> {
    return this.json<DocumentSummary[]>("/documents");
  }

  getDocument(id: string): Promise<DocumentDetail> {
    return this.json<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
  }

  async deleteDocument(id: string): Promise<void> {
    await this.request(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  getJob(documentId: string, jobId: string): Promise<Job> {
    return this.json<Job>(
      `/documents/${encodeURIComponent(documentId)}/jobs/${encodeURIComponent(jobId)}`,
    );
  }

  // -- reading -----------------------------------------------------------

  getPage(documentId: string, pageIndex: number): Promise<Page> {
    return this.json<Page>(`/documents/${encodeURIComponent(documentId)}/pages/${pageIndex}`);
  }

  getSegment(documentId: string, segmentId: string): Promise<Segment> {
    return this.json<Segment>(
      `/documents/${encodeURIComponent(documentId)}/segments/${encodeURIComponent(segmentId)}`,
    );
  }

  async getAudio(documentId: string, segmentId: string, signal?: AbortSignal): Promise<AudioClip> {
    const response = await this.request(
      `/documents/${encodeURIComponent(documentId)}/segments/${encodeURIComponent(segmentId)}/audio`,
      { signal },
    );
    // Absent means unknown, and unknown must not read as "real".
    const realModel = response.headers.get(REAL_MODEL_HEADER) === "true";
    return { blob: await response.blob(), realModel };
  }

  getAudioManifest(documentId: string, segmentId: string): Promise<AudioManifest> {
    return this.json<AudioManifest>(
      `/documents/${encodeURIComponent(documentId)}/segments/${encodeURIComponent(
        segmentId,
      )}/audio/manifest`,
    );
  }

  // -- bookmarks ---------------------------------------------------------

  addBookmark(documentId: string, segmentId: string, note?: string): Promise<Bookmark> {
    return this.json<Bookmark>(`/documents/${encodeURIComponent(documentId)}/bookmarks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_id: segmentId, ...(note ? { note } : {}) }),
    });
  }

  listBookmarks(documentId: string): Promise<Bookmark[]> {
    return this.json<Bookmark[]>(`/documents/${encodeURIComponent(documentId)}/bookmarks`);
  }

  async deleteBookmark(documentId: string, bookmarkId: string): Promise<void> {
    await this.request(
      `/documents/${encodeURIComponent(documentId)}/bookmarks/${encodeURIComponent(bookmarkId)}`,
      { method: "DELETE" },
    );
  }

  // -- progress ----------------------------------------------------------

  saveProgress(documentId: string, segmentId: string, offsetSeconds: number): Promise<Progress> {
    return this.json<Progress>(`/documents/${encodeURIComponent(documentId)}/progress`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_id: segmentId, offset_seconds: offsetSeconds }),
    });
  }

  getProgress(documentId: string): Promise<Progress> {
    return this.json<Progress>(`/documents/${encodeURIComponent(documentId)}/progress`);
  }

  // -- operations --------------------------------------------------------

  readiness(): Promise<Readiness> {
    return this.json<Readiness>("/readiness");
  }
}

/** FastAPI puts the useful part in `detail`; anything else is not shown to a reader. */
async function detailOf(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    return response.statusText;
  } catch {
    return response.statusText;
  }
}
