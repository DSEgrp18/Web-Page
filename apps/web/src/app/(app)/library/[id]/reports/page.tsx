import type { Metadata } from "next";

import { BookReports } from "@/components/BookReports";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.reportsLink };
}

export default async function ReportsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BookReports documentId={id} />;
}
