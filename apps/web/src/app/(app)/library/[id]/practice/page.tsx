import type { Metadata } from "next";

import { Practice } from "@/components/Practice";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.quizzesHeading };

export default async function PracticePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ review?: string }>;
}) {
  const { id } = await params;
  const { review } = await searchParams;
  return <Practice documentId={id} review={review} />;
}
