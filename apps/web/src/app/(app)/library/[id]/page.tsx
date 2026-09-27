import type { Metadata } from "next";

import { Reader } from "@/components/Reader";
import { strings } from "@/lib/strings";

/**
 * Until the book has loaded. The book's own name is private and fetched in the
 * browser, so the reader renames the tab once it has it.
 */
export const metadata: Metadata = { title: strings.readingTitle };

/**
 * Route params arrive as a promise in Next 16. Nothing here renders on the
 * server beyond the id: the document itself is private, and fetching it needs
 * the reader's identity, which lives in the browser.
 */
export default async function ReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    segment?: string | string[];
    quiz?: string | string[];
    question?: string | string[];
  }>;
}) {
  const { id } = await params;
  const { segment, quiz, question } = await searchParams;
  // Arriving from a quiz's "hear the source": a way back to the next question.
  const at = Number.parseInt(typeof question === "string" ? question : "", 10);
  const next = Number.isFinite(at) && at > 0 ? at : 0;
  const backToQuiz =
    typeof quiz === "string" && quiz
      ? `/library/${encodeURIComponent(id)}/practice?quiz=${encodeURIComponent(quiz)}&question=${next}`
      : undefined;
  return (
    <Reader
      documentId={id}
      bookmarkSegmentId={typeof segment === "string" ? segment : undefined}
      backToQuiz={backToQuiz}
    />
  );
}
