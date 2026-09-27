import type { Metadata } from "next";

import { BookReports } from "@/components/BookReports";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.reportsLink };

export default async function ReportsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BookReports documentId={id} />;
}
