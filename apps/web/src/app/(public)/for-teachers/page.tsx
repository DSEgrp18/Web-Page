import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { forTeachers } from "@/lib/content";

export const metadata: Metadata = { title: forTeachers.title };

export default function Page() {
  return <ProsePageView page={forTeachers} />;
}
