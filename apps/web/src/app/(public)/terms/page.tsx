import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { terms } from "@/lib/content";

export const metadata: Metadata = { title: terms.title };

export default function Page() {
  return <ProsePageView page={terms} />;
}
