import type { Metadata } from "next";

import { RecoverForm } from "@/components/AccountForms";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.recoverHeading };

export default function RecoverPage() {
  return <RecoverForm />;
}
