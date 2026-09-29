import type { Metadata } from "next";

import { ClassDetail } from "@/components/ClassDetail";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.classesNav };
}

export default async function ClassPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClassDetail classId={id} />;
}
