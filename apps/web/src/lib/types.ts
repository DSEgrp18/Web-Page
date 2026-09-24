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
  /**
   * What kind of thing this segment is part of.
   *
   * Somebody listening cannot see that a caption has interrupted a paragraph,
   * so the interface has to say it. `unknown` means nothing classified this
   * page, which is different from classifying it as prose.
   */
  role: BlockRole;
  /** Heading depth, 1 outermost. Null for anything that is not a heading. */
  level: number | null;
}

export type BlockRole =
  | "paragraph"
  | "heading"
  | "caption"
  | "list_item"
  | "contents_row"
  | "table_cell"
  | "running_head"
  | "page_number"
  | "address"
  | "unknown";

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
  /**
   * How far through the current stage, in pages. Each stage counts its own
   * pages, so these start again when the stage changes. Null before a stage
   * finishes its first page.
   */
  pages_done: number | null;
  pages_total: number | null;
  /** Whether `retryDocument` would start the book again. */
  can_retry: boolean;
  updated_at: string;
}

/** Where a reader stopped, as the library needs it to draw a progress bar. */
export interface ReadingPosition {
  segment_id: string;
  segment_index: number;
  updated_at: string;
  /** True when the book was reprocessed after this position was saved. */
  stale: boolean;
}

export interface DocumentSummary {
  document_id: string;
  filename: string;
  /** The original upload's media type. */
  media_type?: string;
  /** What the reader named it. Null means they have not; show the filename. */
  title: string | null;
  size_bytes: number;
  created_at: string;
  version: string | null;
  page_count: number;
  segment_count: number;
  /** Null when this reader has never opened the book. */
  reading: ReadingPosition | null;
  /**
   * The latest preparation job. A book with no version is being prepared only
   * while this is queued or running; after a failure it says why.
   */
  job: Job | null;
}

/** Where a chapter opens, as the book prints it. */
export interface Chapter {
  /** The book's own words. May be empty when only a number is printed. */
  title: string;
  /** As printed, so "02" stays "02". */
  number: string | null;
  page_index: number;
}

export interface DocumentDetail extends DocumentSummary {
  notes: string[];
  /**
   * `[]` means the book was examined and has none. `null` means nobody looked
   * (not ready, or prepared before chapters existed). Never announce `null` as
   * "no chapters".
   */
  chapters: Chapter[] | null;
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
  /** How far into the book, resolved when the position was saved. */
  segment_index: number;
  document_version: string;
  updated_at: string;
  /** True when the document was reprocessed after this position was saved. */
  stale: boolean;
}

/** A saved sentence, including enough context to find it again after a reprocess. */
export interface Bookmark {
  bookmark_id: string;
  document_id: string;
  segment_id: string;
  note: string | null;
  created_at: string;
  document_version: string;
  /** True when this record belongs to an earlier extraction of the document. */
  stale: boolean;
  /** False when its sentence no longer exists in the current extraction. */
  segment_found: boolean;
  page_index: number | null;
  page_label: string | null;
  display_text: string | null;
}

/** A passage the study answer quotes, with the precise place it came from. */
export interface StudyCitation {
  passage_id: string;
  page_index: number;
  page_label: string | null;
  section: string | null;
  segment_ids: string[];
  quote: string;
}

/**
 * An earlier question and its answer, sent so a follow-up can be understood.
 * Context for the answerer, never evidence: null when it was not answered.
 */
export interface Exchange {
  question: string;
  answer: string | null;
}

/**
 * A grounded study result. A null answer means the service deliberately
 * abstained rather than reach for something unsupported.
 */
export interface StudyAnswer {
  document_id: string;
  /**
   * An exact passage from the document when `generated` is false, or Sinhala
   * prose written from the cited passages when it is true.
   */
  answer: string | null;
  citations: StudyCitation[];
  abstained: boolean;
  /**
   * True when a model wrote the answer rather than the book supplying it.
   *
   * The interface must label the two differently. A reader who cannot see the
   * page has no other way to tell whose words these are, and "the book says
   * this" and "a model wrote this from the book" are different claims.
   */
  generated: boolean;
}

export type Role = "student" | "teacher" | "admin";

/** Who is signed in. Never a password, a hash, or the session itself. */
export interface Account {
  user_id: string;
  email: string;
  display_name: string;
  role: Role;
  /** False for accounts made before recovery codes, until they make one. */
  has_recovery_code: boolean;
  created_at: string;
}

/** A new session. The session is a cookie; this is what the page may know. */
export interface SignedIn {
  /** Always null for a browser: the session is an httpOnly cookie. */
  token: string | null;
  expires_at: string;
  account: Account;
  /** Sent back in X-CSRF-Token on every change. */
  csrf_token: string;
  /** Only when an account is made or recovered, and shown once. */
  recovery_code: string | null;
}

// -- classes and sharing ----------------------------------------------------

/** A student as their teacher sees them: a name and a standing, no more. */
export interface MemberDetail {
  user_id: string;
  display_name: string;
  state: "pending" | "active" | "removed";
  share_progress: boolean;
  joined_at: string;
}

/** A class as its teacher sees it, with the code to give out. */
export interface TaughtClass {
  class_id: string;
  name: string;
  join_code: string;
  created_at: string;
  members: MemberDetail[];
}

/** A class as its student sees it. No code, no other students. */
export interface JoinedClass {
  class_id: string;
  name: string;
  teacher_name: string;
  state: "pending" | "active";
  share_progress: boolean;
}

export interface MyClasses {
  teaching: TaughtClass[];
  joined: JoinedClass[];
}

/** A book shared with one of this reader's classes. */
export interface ClassBook {
  class_id: string;
  class_name: string;
  book: DocumentSummary;
}

export interface FlaggedPage {
  page_index: number;
  page_label: string | null;
  quality: string;
  notes: string[];
  decision: "accepted" | "withheld" | null;
}

/** The flagged pages a teacher decides on before sharing. */
export interface Review {
  version: string;
  pages: FlaggedPage[];
  undecided: number;
  ready_to_publish: boolean;
}

export type RightsBasis =
  "public_domain" | "government_textbook" | "publisher_permission" | "own_work" | "other";

export interface PublicationDetail {
  version: string;
  basis: RightsBasis;
  note: string | null;
  attested_at: string;
  published_at: string;
  class_ids: string[];
  /** True when the book has changed since it was shared. */
  stale: boolean;
}

export interface Readiness {
  alive: boolean;
  serving: boolean;
  readiness: string;
  real_model: boolean;
  model_version: string | null;
  /** Who finds headings and paragraphs: "deterministic", or "gemini" (Google). */
  structure: string;
  /** Scanned pages read from their image: "off", "broken" or "all". Always local. */
  ocr: string;
  /** Who writes answers: "extractive" (the book's words), or "gemini" (Google). */
  answers: string;
  auth_mode: string;
  limitations: string[];
}

/** Audio, with the one fact a listener cannot work out for themselves. */
export interface AudioClip {
  blob: Blob;
  /** From `X-Reader-Real-Model`. False means a tone. */
  realModel: boolean;
}
