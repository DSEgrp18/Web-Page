import type { Metadata } from "next";

import { RegisterForm } from "@/components/AccountForms";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.registerHeading };
}

export default function RegisterPage() {
  return <RegisterForm />;
}
