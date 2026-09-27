/**
 * Chapters saved for listening without a network.
 *
 * Everything lives in Cache Storage under this site's origin: each clip under
 * the same URL the reader fetches it from, and one small JSON entry per saved
 * chapter describing it. Nothing is saved without the reader asking, and every
 * cache is deleted when they sign out (ReaderProvider), because phones are
 * shared.
 */

import { API_BASE } from "@/lib/client";
import type { OfflineManifest } from "@/lib/types";

export const DOWNLOADS = "swara-downloads-v1";
export const SHELL = "swara-shell-v1";
const ENTRIES = "/offline-entries/";

export interface SavedClip {
  segment_id: string;
  text: string;
  page_label: string | null;
  /** Null when the sentence had no audio when it was saved. */
  url: string | null;
}

export interface SavedChapter {
  key: string;
  document_id: string;
  title: string;
  chapter: string | null;
  version: string;
  clips: SavedClip[];
  bytes: number;
  saved_at: string;
}

export function offlineSupported(): boolean {
  return typeof caches !== "undefined";
}

export function audioUrl(documentId: string, segmentId: string): string {
  return `${API_BASE}/documents/${encodeURIComponent(documentId)}/segments/${encodeURIComponent(segmentId)}/audio`;
}

function entryUrl(key: string): string {
  return `${ENTRIES}${encodeURIComponent(key)}`;
}

/**
 * Save every clip that has audio, then the entry that describes them. The
 * entry goes last, so a download interrupted halfway is never listed as saved.
 */
export async function saveChapter(
  manifest: OfflineManifest,
  onProgress: (done: number, total: number) => void = () => {},
  fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
): Promise<SavedChapter> {
  const cache = await caches.open(DOWNLOADS);
  const ready = manifest.clips.filter((clip) => clip.ready);
  let bytes = 0;
  let done = 0;
  const saved = new Set<string>();
  for (const clip of ready) {
    const url = audioUrl(manifest.document_id, clip.segment_id);
    const response = await fetchImpl(url, { credentials: "same-origin" });
    if (response.ok) {
      const body = await response.arrayBuffer();
      bytes += body.byteLength;
      await cache.put(
        url,
        new Response(body, {
          headers: { "Content-Type": response.headers.get("Content-Type") ?? "audio/wav" },
        }),
      );
      saved.add(clip.segment_id);
    }
    done += 1;
    onProgress(done, ready.length);
  }
  const entry: SavedChapter = {
    key: `${manifest.document_id}:${manifest.first_page}`,
    document_id: manifest.document_id,
    title: manifest.title,
    chapter: manifest.chapter,
    version: manifest.version,
    clips: manifest.clips.map((clip) => ({
      segment_id: clip.segment_id,
      text: clip.text,
      page_label: clip.page_label,
      url: saved.has(clip.segment_id) ? audioUrl(manifest.document_id, clip.segment_id) : null,
    })),
    bytes,
    saved_at: new Date().toISOString(),
  };
  await cache.put(
    entryUrl(entry.key),
    new Response(JSON.stringify(entry), { headers: { "Content-Type": "application/json" } }),
  );
  await warmShell(fetchImpl);
  return entry;
}

/**
 * Keep the offline page and the files it runs on, so it opens with no network.
 * Best effort: a failure here leaves the audio saved and the page reachable
 * whenever there is a network.
 */
async function warmShell(fetchImpl: typeof fetch): Promise<void> {
  try {
    const shell = await caches.open(SHELL);
    const page = await fetchImpl("/offline", { credentials: "same-origin" });
    if (!page.ok) return;
    const html = await page.clone().text();
    await shell.put("/offline", page);
    const assets = new Set(html.match(/\/_next\/static\/[^"'\s)]+/g) ?? []);
    for (const asset of assets) {
      const response = await fetchImpl(asset);
      if (response.ok) await shell.put(asset, response);
    }
  } catch {
    // The shell is a convenience; the saved audio is what matters.
  }
}

export async function listSaved(): Promise<SavedChapter[]> {
  if (!offlineSupported()) return [];
  const cache = await caches.open(DOWNLOADS);
  const entries: SavedChapter[] = [];
  for (const request of await cache.keys()) {
    if (!new URL(request.url, "http://x").pathname.startsWith(ENTRIES)) continue;
    const response = await cache.match(request);
    if (response) entries.push((await response.json()) as SavedChapter);
  }
  return entries.sort((a, b) => b.saved_at.localeCompare(a.saved_at));
}

export async function removeSaved(entry: SavedChapter): Promise<void> {
  const cache = await caches.open(DOWNLOADS);
  const others = (await listSaved()).filter((e) => e.key !== entry.key);
  const stillUsed = new Set(others.flatMap((e) => e.clips.map((c) => c.url)));
  for (const clip of entry.clips) {
    if (clip.url && !stillUsed.has(clip.url)) await cache.delete(clip.url);
  }
  await cache.delete(entryUrl(entry.key));
}

/** A saved clip, ready to play, or null if it is not in the cache. */
export async function savedClip(url: string): Promise<Blob | null> {
  const cache = await caches.open(DOWNLOADS);
  const response = await cache.match(url);
  return response ? response.blob() : null;
}
