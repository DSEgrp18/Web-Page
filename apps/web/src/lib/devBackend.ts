import { FakeServer, readablePage, segment } from "../../tests/fakeApi";

/**
 * A stand-in API for working on the interface with no backend running.
 *
 * Only when `READER_DEV_FAKE=1` and never in a production build. It is the
 * test suite's fake, already signed in as a teacher with a few books, kept in
 * memory: restarting the dev server starts it over. Nothing here is real
 * extraction, voice, or answers, and the PDF view has no real file to draw.
 */
export const DEV_FAKE_ENV = "READER_DEV_FAKE";

export function devFakeEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return env.NODE_ENV !== "production" && env[DEV_FAKE_ENV] === "1";
}

const USER = "usr-dev";

function seeded(): FakeServer {
  const server = new FakeServer({
    books: [
      {
        document_id: "doc-history",
        filename: "ඉතිහාසය-10-ශ්‍රේණිය.pdf",
        title: "ඉතිහාසය — 10 ශ්‍රේණිය",
        version: "v1",
        pages: [
          {
            ...readablePage(0, [], "1"),
            segments: [
              segment(0, 0, "කාර්මික විප්ලවය", "1", "heading", 1),
              segment(0, 1, "දහඅටවන සියවසේ එංගලන්තයේ කර්මාන්ත ශීඝ්‍රයෙන් වෙනස් විය.", "1"),
              segment(0, 2, "වාෂ්ප එන්ජිම නිෂ්පාදනය වේගවත් කළේය.", "1"),
            ],
          },
          readablePage(1, ["නගර ශීඝ්‍රයෙන් වර්ධනය විය.", "කම්කරුවන් ගම්වලින් නගරවලට පැමිණියහ."], "2"),
          readablePage(2, ["ජාතික පුනරුදය ලංකාවේ ද ඇති විය.", "පාසල් සහ පුවත්පත් බිහි විය."], "3"),
        ],
        chapters: [
          { title: "කාර්මික විප්ලවය", number: "01", page_index: 0 },
          { title: "ජාතික පුනරුදය", number: "02", page_index: 2 },
        ],
        reading: {
          segment_id: "0001-s0",
          segment_index: 3,
          updated_at: "2026-10-07T18:00:00Z",
          stale: false,
        },
      },
      {
        document_id: "doc-science",
        filename: "විද්‍යාව.pdf",
        version: "v1",
        pages: [
          readablePage(0, ["සියලු ජීවීන් සෛල වලින් සෑදී ඇත.", "සෛලය ජීවයේ මූලික ඒකකයයි."], "12"),
        ],
      },
      {
        document_id: "doc-preparing",
        filename: "භූගෝල විද්‍යාව.pdf",
        version: null,
        pages: [],
        job: { stage: "extract", pages_done: 4, pages_total: 20 },
      },
    ],
  });
  server.accounts.push({
    user_id: USER,
    email: "dev@swara.local",
    password: "dev-password-123",
    display_name: "නිමලි",
  });
  server.teachers.add(USER);
  server.classes.push({
    class_id: "cls-10a",
    name: "10 ශ්‍රේණිය A",
    join_code: "12345678",
    teacher: USER,
    members: [
      {
        user_id: "usr-kamal",
        display_name: "කමල්",
        state: "active",
        share_progress: true,
        joined_at: "2026-09-10T00:00:00Z",
      },
      {
        user_id: "usr-sachini",
        display_name: "සචිනි",
        state: "pending",
        share_progress: false,
        joined_at: "2026-10-01T00:00:00Z",
      },
    ],
  });
  server.signedInAs = USER;
  return server;
}

const holder = globalThis as unknown as { __swaraDevBackend?: FakeServer };

/** One fake per dev-server process, kept across hot reloads. */
function backend(): FakeServer {
  holder.__swaraDevBackend ??= seeded();
  return holder.__swaraDevBackend;
}

/** Answer an `/api/...` request from the fake. */
export async function devFakeAnswer(request: Request, path: string[]): Promise<Response> {
  const url = new URL(request.url);
  const target = `/${path.map(encodeURIComponent).join("/")}${url.search}`;
  let body: BodyInit | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = (request.headers.get("content-type") ?? "").startsWith("multipart/form-data")
      ? await request.formData()
      : (await request.text()) || undefined;
  }
  return backend().fetch(target, { method: request.method, headers: request.headers, body });
}
