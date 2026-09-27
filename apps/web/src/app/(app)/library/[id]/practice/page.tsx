import type { Metadata } from "next";

import { Practice } from "@/components/Practice";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.quizzesHeading };

export default async function PracticePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ review?: string; quiz?: string; question?: string }>;
}) {
  const { id } = await params;
  const { review, quiz, question } = await searchParams;
  // Back from "hear the source": the quiz, at the question after the one
  // whose source was heard. Anything unparseable starts at the beginning.
  const at = Number.parseInt(question ?? "", 10);
  const resume = quiz ? { quiz, question: Number.isFinite(at) && at > 0 ? at : 0 } : undefined;
  return <Practice documentId={id} review={review} resume={resume} />;
}
