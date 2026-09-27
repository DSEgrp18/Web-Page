import type { Metadata } from "next";

import { Progress } from "@/components/Progress";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.progressHeading };

export default function ProgressPage() {
  return <Progress />;
}
