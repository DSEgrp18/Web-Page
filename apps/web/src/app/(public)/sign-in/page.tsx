import type { Metadata } from "next";

import { SignInForm } from "@/components/AccountForms";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.signInHeading };
}

export default function SignInPage() {
  return <SignInForm />;
}
