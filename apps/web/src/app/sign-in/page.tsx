import type { Metadata } from "next";

import { SignInForm } from "@/components/AccountForms";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.signInHeading };

export default function SignInPage() {
  return <SignInForm />;
}
