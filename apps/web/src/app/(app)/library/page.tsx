import type { Metadata } from "next";

import { Library } from "@/components/Library";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.libraryHeading };

export default function LibraryPage() {
  return <Library />;
}
