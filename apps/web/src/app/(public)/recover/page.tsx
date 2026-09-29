import type { Metadata } from "next";

import { RecoverForm } from "@/components/AccountForms";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.recoverHeading };
}

export default function RecoverPage() {
  return <RecoverForm />;
}
