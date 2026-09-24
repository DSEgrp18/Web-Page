import type { Metadata } from "next";

import { Practice } from "@/components/Practice";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.quizzesHeading };

export default async function PracticePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Practice documentId={id} />;
}
