import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { accessibility } from "@/lib/content";

export const metadata: Metadata = { title: accessibility.title };

export default function Page() {
  return <ProsePageView page={accessibility} report />;
}
