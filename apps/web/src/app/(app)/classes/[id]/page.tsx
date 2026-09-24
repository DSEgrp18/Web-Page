import type { Metadata } from "next";

import { ClassDetail } from "@/components/ClassDetail";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.classesNav };

export default async function ClassPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClassDetail classId={id} />;
}
