import type { Metadata } from "next";

import { BookSearch } from "@/components/BookSearch";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.searchLink };

export default async function SearchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BookSearch documentId={id} />;
}
