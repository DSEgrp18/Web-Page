import type { Metadata } from "next";

import { Library } from "@/components/Library";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.libraryHeading };
}

export default function LibraryPage() {
  return <Library />;
}
