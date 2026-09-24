import type { Metadata } from "next";

import { ShareBook } from "@/components/ShareBook";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.shareBook };

export default async function SharePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ShareBook documentId={id} />;
}
