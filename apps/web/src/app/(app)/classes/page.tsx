import type { Metadata } from "next";

import { Classes } from "@/components/Classes";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.classesHeading };

export default function ClassesPage() {
  return <Classes />;
}
