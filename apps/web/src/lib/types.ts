/**
 * The reader API's contract, as the browser sees it.
 *
 * These mirror `services/api/src/sinhala_reader/schemas.py` field for field.
 * They are written by hand rather than generated because the generator would
 * be one more thing to install and keep running; `npm run verify:contract`
 * checks them against the live server's OpenAPI schema instead, so drift is
 * caught by a check rather than by a reader hearing nothing.
 */

/** A rectangle on the page, measured downwards from the top. */
export interface Box {
  x0: number;
  top: number;
  x1: number;
  bottom: number;
}

/** One thing the reader plays, highlights, or resumes at. */
export interface Segment {
  segment_id: string;
  index: number;
  page_index: number;
  /** The page number as printed, when the book declares one. Not the file position. */
  page_label: string | null;
  /** What a reader sees, and what highlighting points at. */
  display_text: string;
  /** Normalised Sinhala with numbers written out. */
  spoken_text: string;
  boxes: Box[];
}

export type PageKind = "text" | "image" | "mixed" | "empty";
export type Quality = "accepted" | "needs_review" | "undecodable";

export interface Page {
  page_index: number;
  page_label: string | null;
  kind: PageKind;
  quality: Quality;
  /** What a reader loses on this page, in words fit to announce. */
  notes: string[];
  segments: Segment[];
}

export type JobState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  job_id: string;
  kind: string;
  state: JobState;
  stage: string;
  /** Why it failed. Never contains document text. */
  detail: string | null;
  updated_at: string;
}

export interface DocumentSummary {
  document_id: string;
  filename: string;
  size_bytes: number;
  created_at: string;
  version: string | null;
  page_count: number;
  segment_count: number;
}

export interface DocumentDetail extends DocumentSummary {
  notes: string[];
  job: Job | null;
}

export interface AudioManifest {
  segment_id: string;
  cache_key: string;
  generated: boolean;
  /** False means a placeholder tone, not speech. Never present it as narration. */
  real_model: boolean;
  voice_id: string | null;
  model_version: string | null;
  duration_seconds: number | null;
}

export interface Progress {
  document_id: string;
  segment_id: string;
  offset_seconds: number;
  document_version: string;
  updated_at: string;
  /** True when the document was reprocessed after this position was saved. */
  stale: boolean;
}

export interface Readiness {
  alive: boolean;
  serving: boolean;
  readiness: string;
  real_model: boolean;
  model_version: string | null;
  auth_mode: string;
  limitations: string[];
}

/** Audio, with the one fact a listener cannot work out for themselves. */
export interface AudioClip {
  blob: Blob;
  /** From `X-Reader-Real-Model`. False means a tone. */
  realModel: boolean;
}
