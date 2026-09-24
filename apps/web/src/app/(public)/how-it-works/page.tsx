import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { howItWorks } from "@/lib/content";

export const metadata: Metadata = { title: howItWorks.title };

export default function Page() {
  return <ProsePageView page={howItWorks} />;
}
