import type { Metadata } from "next";

import { PasteText } from "@/components/PasteText";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.pasteHeading };

export default function PastePage() {
  return <PasteText />;
}
