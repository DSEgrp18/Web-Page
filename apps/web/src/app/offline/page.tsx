import type { Metadata } from "next";

import { PublicFrame } from "@/components/PublicFrame";
import { OfflineLibrary } from "@/components/OfflineLibrary";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.offlineNav };

/** Outside the signed-in routes: it must open with no network and no session check. */
export default function OfflinePage() {
  return (
    <PublicFrame>
      <OfflineLibrary />
    </PublicFrame>
  );
}
