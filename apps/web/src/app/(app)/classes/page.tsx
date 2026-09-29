import type { Metadata } from "next";

import { Classes } from "@/components/Classes";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.classesHeading };
}

export default async function ClassesPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string | string[] }>;
}) {
  const { code } = await searchParams;
  // From a class link (`/join/<code>`): digits only, never anything else.
  const digits = typeof code === "string" ? code.replace(/\D/g, "").slice(0, 8) : "";
  return <Classes joinCode={digits || undefined} />;
}
