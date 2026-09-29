import type { Metadata } from "next";

import { Progress } from "@/components/Progress";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.progressHeading };
}

export default function ProgressPage() {
  return <Progress />;
}
