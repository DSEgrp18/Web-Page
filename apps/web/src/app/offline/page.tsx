import type { Metadata } from "next";

import { PublicFrame } from "@/components/PublicFrame";
import { OfflineLibrary } from "@/components/OfflineLibrary";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.offlineNav };
}

/** Outside the signed-in routes: it must open with no network and no session check. */
export default function OfflinePage() {
  return (
    <PublicFrame>
      <OfflineLibrary />
    </PublicFrame>
  );
}
