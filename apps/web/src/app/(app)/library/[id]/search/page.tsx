import type { Metadata } from "next";

import { BookSearch } from "@/components/BookSearch";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.searchLink };
}

export default async function SearchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BookSearch documentId={id} />;
}
