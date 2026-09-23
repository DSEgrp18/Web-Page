/**
 * The same-origin pass-through to the reader API. Server-only.
 *
 * The browser talks only to this site, at `/api/...`, and this forwards to the
 * API. That is what lets the session live in an httpOnly cookie (a script in
 * the page, where pdf.js renders untrusted PDFs, cannot read it), and it
 * removes CORS altogether. See the product plan, section 6.2.
 *
 * A route handler, not `rewrites()`, for three reasons: rewrites are compiled
 * at build time, which stops one image being promoted from staging to
 * production; their proxy gives up at 30 seconds, and a study answer can take
 * 90; and the request proxy buffers bodies to 10 MB, and an upload may be 200.
 *
 * What crosses, in either direction, is an allow-list. In particular, anything
 * a browser sends claiming an identity (`X-Reader-User`, `Authorization`) or
 * asking for a readable token (`X-Session-Transport`) is dropped: behind this,
 * the cookie is the only credential.
 */

/** Environment variables, as a plain lookup so a test can pass its own. */
type Env = Record<string, string | undefined>;

/** Where the API is, read at run time on the server. Never sent to a browser. */
export const API_URL_ENV = "READER_API_URL";

/**
 * "1" when a proxy in front of this app writes the reader's address into
 * `X-Forwarded-For` (Azure does). Without one, that header is whatever the
 * client typed, so it is not passed on, and the API limits by this server's
 * address instead: stricter, never looser.
 */
export const BEHIND_PROXY_ENV = "READER_BEHIND_PROXY";

export const TIMEOUT_MS = 120_000;

const REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "if-range",
  "range",
  "sec-fetch-dest",
  "sec-fetch-mode",
  "sec-fetch-site",
  "user-agent",
  "x-csrf-token",
];

const RESPONSE_HEADERS = [
  "accept-ranges",
  "cache-control",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "retry-after",
  "www-authenticate",
  "x-reader-real-model",
];

function problem(status: number, detail: string): Response {
  return Response.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

/** The API address for a path under `/api`, or null if it is not configured. */
export function targetFor(
  requestUrl: string,
  path: string[],
  base: string | undefined,
): string | null {
  if (!base) return null;
  const search = new URL(requestUrl).search;
  const encoded = path.map((part) => encodeURIComponent(part)).join("/");
  return `${base.replace(/\/+$/, "")}/${encoded}${search}`;
}

export function forwardedHeaders(incoming: Headers, env: Env = process.env): Headers {
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = incoming.get(name);
    if (value !== null) headers.set(name, value);
  }
  if (env[BEHIND_PROXY_ENV] === "1") {
    // The address the nearest proxy saw: the last entry, which it appended.
    // Anything before it came from the client and proves nothing.
    const last = (incoming.get("x-forwarded-for") ?? "").split(",").pop()?.trim();
    if (last) headers.set("x-forwarded-for", last);
  }
  return headers;
}

export function returnedHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.get(name);
    if (value !== null) headers.set(name, value);
  }
  // Several cookies must stay several headers; joining them with commas, as
  // `get` does, breaks any cookie whose expiry date contains a comma.
  for (const cookie of upstream.getSetCookie()) headers.append("set-cookie", cookie);
  return headers;
}

/** Forward one request and stream the answer back. */
export async function passThrough(
  request: Request,
  path: string[],
  {
    env = process.env,
    fetchImpl = fetch,
    timeoutMs = TIMEOUT_MS,
  }: { env?: Env; fetchImpl?: typeof fetch; timeoutMs?: number } = {},
): Promise<Response> {
  const target = targetFor(request.url, path, env[API_URL_ENV]);
  if (!target) return problem(503, "The reading service is not configured.");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const timeout = AbortSignal.timeout(timeoutMs);
  let upstream: Response;
  try {
    upstream = await fetchImpl(target, {
      method: request.method,
      headers: forwardedHeaders(request.headers, env),
      // Streamed, never buffered: an upload may be 200 MB.
      body: hasBody ? request.body : undefined,
      // @ts-expect-error `duplex` is required by Node's fetch to stream a body,
      // and is not in the DOM's RequestInit yet.
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
      signal: AbortSignal.any([request.signal, timeout]),
    });
  } catch (cause) {
    if (timeout.aborted) return problem(504, "The reading service took too long to answer.");
    if (request.signal.aborted) return problem(499, "The request was cancelled.");
    console.error("pass-through: the API could not be reached", cause);
    return problem(502, "The reading service is not answering.");
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: returnedHeaders(upstream.headers),
  });
}
