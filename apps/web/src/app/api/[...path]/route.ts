import { passThrough } from "@/lib/passThrough";

/**
 * Every request to `/api/...` goes to the reader API, from this server.
 * The work, and the reasons, are in `lib/passThrough.ts`.
 */

// Runs per request, on Node: a body is streamed through, and the API address
// is read at run time, so one build serves staging and production.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: Request, { params }: Context): Promise<Response> {
  const { path } = await params;
  return passThrough(request, path);
}

export const GET = handle;
export const HEAD = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
