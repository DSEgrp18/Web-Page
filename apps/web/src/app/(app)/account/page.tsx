import type { Metadata } from "next";

import { AccountSettings } from "@/components/AccountSettings";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.accountHeading };

export default function AccountPage() {
  return <AccountSettings />;
}
