import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { help } from "@/lib/content";

export const metadata: Metadata = { title: help.title };

export default function Page() {
  return <ProsePageView page={help} report />;
}
