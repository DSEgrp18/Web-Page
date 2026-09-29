import type { Metadata } from "next";

import { AccountSettings } from "@/components/AccountSettings";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.accountHeading };
}

export default function AccountPage() {
  return <AccountSettings />;
}
