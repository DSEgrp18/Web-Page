import type { Metadata } from "next";

import { ShareBook } from "@/components/ShareBook";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.shareBook };
}

export default async function SharePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ShareBook documentId={id} />;
}
