/**
 * Talking to the reader API.
 *
 * Two decisions worth knowing about:
 *
 * **It talks only to this site.** Every request goes to `/api/...`, which the
 * web server passes on to the API (`lib/passThrough.ts`). The session is an
 * httpOnly cookie the browser sends by itself and no script can read; what the
 * client adds is the CSRF token, on every change, which it is handed at sign-in
 * and by `/auth/me` and never stores.
 *
 * **Audio is fetched, not pointed at.** An `<audio src>` cannot read
 * `X-Reader-Real-Model`, so audio comes back through `fetch` as a blob, and the
 * "is this actually speech" answer travels with it instead of being looked up
 * separately and possibly forgotten.
 *
 * **Failures become a small set of named kinds.** The interface has to say
 * something out loud for each one, in Sinhala, and it must never guess: the API
 * answers 404 for a document that does not exist *and* for one belonging to
 * someone else, deliberately, so the reader is told "not found" and nothing more.
 */

import type {
  Account,
  AudioClip,
  ClassBook,
  JoinedClass,
  MyClasses,
  PublicationDetail,
  Review,
  RightsBasis,
  TaughtClass,
  AudioManifest,
  Bookmark,
  DocumentDetail,
  DocumentSummary,
  Exchange,
  Job,
  Page,
  Progress,
  Readiness,
  Segment,
  SignedIn,
  StudyAnswer,
} from "./types";

export type FailureKind =
  | "offline" // the request never reached a server
  | "signed_out" // no session, or it has ended: sign in again
  | "forbidden" // the page's CSRF token is out of date: reload
  | "throttled" // too many attempts: wait, then try again
  | "not_found" // no such document, page, or segment — for this reader
  | "not_ready" // the document is still being prepared
  | "rejected" // the upload itself was refused
  | "unspeakable" // this segment has nothing to say
  | "server"; // anything else

export class ApiError extends Error {
  readonly kind: FailureKind;
  readonly status: number;
  /** For `throttled`: seconds until trying again is allowed, when the server said. */
  readonly retryAfter: number | null;

  constructor(
    kind: FailureKind,
    status: number,
    message: string,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function kindFor(status: number): FailureKind {
  if (status === 401) return "signed_out";
  if (status === 403) return "forbidden";
  if (status === 429) return "throttled";
  if (status === 404) return "not_found";
  if (status === 409) return "not_ready";
  if (status === 422) return "unspeakable";
  if (status === 400 || status === 413 || status === 415) return "rejected";
  return "server";
}

/** Where the API is, as this site serves it: the same-origin pass-through. */
export const API_BASE = "/api";

export const CSRF_HEADER = "X-CSRF-Token";
export const REAL_MODEL_HEADER = "X-Reader-Real-Model";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

/** One request to the API, with failures turned into named kinds. */
async function send(
  options: ClientOptions,
  csrf: string | null,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = (options.baseUrl ?? API_BASE).replace(/\/+$/, "");
  const doFetch = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (csrf && UNSAFE_METHODS.has(method)) headers.set(CSRF_HEADER, csrf);

  let response: Response;
  try {
    // Same origin, so the browser sends the session cookie by itself.
    response = await doFetch(`${base}${path}`, { ...init, headers, credentials: "same-origin" });
  } catch (cause) {
    throw new ApiError("offline", 0, String(cause));
  }
  if (!response.ok) {
    const retryAfter = Number(response.headers.get("retry-after"));
    throw new ApiError(
      kindFor(response.status),
      response.status,
      await detailOf(response),
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    );
  }
  return response;
}

/**
 * The account routes. Separate from `ReaderApi` because they run before there
 * is a session, and so before there is a CSRF token to send.
 */
export class AuthApi {
  constructor(private readonly options: ClientOptions = {}) {}

  private async json<T>(path: string, init?: RequestInit, csrf: string | null = null): Promise<T> {
    return (await send(this.options, csrf, path, init)).json() as Promise<T>;
  }

  private post<T>(path: string, body: unknown, csrf: string | null = null): Promise<T> {
    return this.json<T>(
      path,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      csrf,
    );
  }

  /** Who is signed in, and the page's CSRF token; null when nobody is. */
  async me(): Promise<{ account: Account; csrf: string } | null> {
    try {
      const { csrf_token, ...account } = await this.json<Account & { csrf_token: string | null }>(
        "/auth/me",
      );
      return { account, csrf: csrf_token ?? "" };
    } catch (error) {
      if (error instanceof ApiError && error.kind === "signed_out") return null;
      throw error;
    }
  }

  signIn(email: string, password: string): Promise<SignedIn> {
    return this.post<SignedIn>("/auth/login", { email, password });
  }

  register(email: string, password: string, displayName: string): Promise<SignedIn> {
    return this.post<SignedIn>("/auth/register", {
      email,
      password,
      display_name: displayName,
    });
  }

  recover(email: string, recoveryCode: string, newPassword: string): Promise<SignedIn> {
    return this.post<SignedIn>("/auth/recover", {
      email,
      recovery_code: recoveryCode,
      new_password: newPassword,
    });
  }

  async signOut(csrf: string): Promise<void> {
    await send(this.options, csrf, "/auth/logout", { method: "POST" });
  }

  /** Change the password. The server ends every session, this one included. */
  async changePassword(csrf: string, currentPassword: string, newPassword: string): Promise<void> {
    await send(this.options, csrf, "/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  /** A new recovery code; the old one stops working. Shown once. */
  async newRecoveryCode(csrf: string, currentPassword: string): Promise<string> {
    const { recovery_code } = await this.post<{ recovery_code: string }>(
      "/auth/recovery-code",
      { current_password: currentPassword },
      csrf,
    );
    return recovery_code;
  }

  async signOutEverywhere(csrf: string): Promise<void> {
    await send(this.options, csrf, "/auth/logout-everywhere", { method: "POST" });
  }

  /** Every book and everything made from it, then the account. Not undoable. */
  async deleteAccount(csrf: string, currentPassword: string): Promise<void> {
    await send(this.options, csrf, "/auth/account", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword }),
    });
  }
}

export class ReaderApi {
  private readonly options: ClientOptions;
  private csrf: string | null;

  /** `csrf` is the page's token, sent on every change; null before sign-in. */
  constructor(csrf: string | null, options: ClientOptions = {}) {
    this.csrf = csrf;
    this.options = options;
  }

  /**
   * The token for the session that has just begun or ended. Set on the same
   * client rather than by making a new one, so nothing that depends on the
   * client fetches again because a token arrived.
   */
  setCsrf(csrf: string | null): void {
    this.csrf = csrf;
  }

  get csrfToken(): string | null {
    return this.csrf;
  }

  private request(path: string, init: RequestInit = {}): Promise<Response> {
    return send(this.options, this.csrf, path, init);
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

  /**
   * Prepare a book again from the file already uploaded, after a failure.
   * Only offered when the latest job says `can_retry`; the server refuses
   * otherwise.
   */
  retryDocument(id: string): Promise<DocumentDetail> {
    return this.json<DocumentDetail>(`/documents/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    });
  }

  /** Give a book the reader's own name. Blank clears it back to the filename. */
  renameDocument(id: string, title: string): Promise<DocumentDetail> {
    return this.json<DocumentDetail>(`/documents/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  }

  /**
   * The uploaded PDF itself, as a blob URL the caller owns.
   *
   * The caller must call `URL.revokeObjectURL` when it is finished, or the
   * whole PDF stays in memory for the life of the tab.
   */
  async getDocumentFile(id: string, signal?: AbortSignal): Promise<Blob> {
    const response = await this.request(`/documents/${encodeURIComponent(id)}/file`, { signal });
    return response.blob();
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

  // -- study -------------------------------------------------------------

  /**
   * Ask about one book. `history` is the recent conversation, so that "and the
   * list of them?" can be understood; it is omitted when empty, which keeps a
   * first question's request exactly what it always was.
   */
  askQuestion(
    documentId: string,
    question: string,
    history: readonly Exchange[] = [],
  ): Promise<StudyAnswer> {
    return this.json<StudyAnswer>(`/documents/${encodeURIComponent(documentId)}/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(history.length > 0 ? { question, history } : { question }),
    });
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

  // -- classes -----------------------------------------------------------

  private send<T>(path: string, method: string, body?: unknown): Promise<T> {
    return this.json<T>(path, {
      method,
      ...(body === undefined
        ? {}
        : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
  }

  myClasses(): Promise<MyClasses> {
    return this.json<MyClasses>("/classes");
  }

  getClass(id: string): Promise<TaughtClass | JoinedClass> {
    return this.json<TaughtClass | JoinedClass>(`/classes/${encodeURIComponent(id)}`);
  }

  createClass(name: string): Promise<TaughtClass> {
    return this.send<TaughtClass>("/classes", "POST", { name });
  }

  renameClass(id: string, name: string): Promise<TaughtClass> {
    return this.send<TaughtClass>(`/classes/${encodeURIComponent(id)}`, "PATCH", { name });
  }

  async deleteClass(id: string): Promise<void> {
    await this.request(`/classes/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  newJoinCode(id: string): Promise<TaughtClass> {
    return this.send<TaughtClass>(`/classes/${encodeURIComponent(id)}/code`, "POST");
  }

  setMember(id: string, userId: string, action: "approve" | "remove"): Promise<TaughtClass> {
    return this.send<TaughtClass>(
      `/classes/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}/${action}`,
      "POST",
    );
  }

  joinClass(code: string): Promise<JoinedClass> {
    return this.send<JoinedClass>("/classes/join", "POST", { code });
  }

  shareProgress(id: string, share: boolean): Promise<JoinedClass> {
    return this.send<JoinedClass>(`/classes/${encodeURIComponent(id)}/share-progress`, "PUT", {
      share,
    });
  }

  async leaveClass(id: string): Promise<void> {
    await this.request(`/classes/${encodeURIComponent(id)}/membership`, { method: "DELETE" });
  }

  classBooks(): Promise<ClassBook[]> {
    return this.json<ClassBook[]>("/class-books");
  }

  // -- sharing a book ------------------------------------------------------

  getReview(documentId: string): Promise<Review> {
    return this.json<Review>(`/documents/${encodeURIComponent(documentId)}/review`);
  }

  decidePage(
    documentId: string,
    pageIndex: number,
    decision: "accepted" | "withheld",
  ): Promise<Review> {
    return this.send<Review>(
      `/documents/${encodeURIComponent(documentId)}/review/${pageIndex}`,
      "PUT",
      { decision },
    );
  }

  getPublication(documentId: string): Promise<PublicationDetail | null> {
    return this.json<PublicationDetail | null>(
      `/documents/${encodeURIComponent(documentId)}/publication`,
    );
  }

  publish(
    documentId: string,
    classIds: string[],
    basis: RightsBasis,
    note: string | null,
  ): Promise<PublicationDetail> {
    return this.send<PublicationDetail>(
      `/documents/${encodeURIComponent(documentId)}/publish`,
      "POST",
      { class_ids: classIds, basis, note },
    );
  }

  async unpublish(documentId: string, classId: string): Promise<void> {
    await this.request(
      `/documents/${encodeURIComponent(documentId)}/classes/${encodeURIComponent(classId)}`,
      { method: "DELETE" },
    );
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
