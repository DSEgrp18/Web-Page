import type { Metadata } from "next";

import { RegisterForm } from "@/components/AccountForms";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.registerHeading };

export default function RegisterPage() {
  return <RegisterForm />;
}
