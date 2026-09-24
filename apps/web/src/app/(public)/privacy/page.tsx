import type { Metadata } from "next";

import { ProcessingNow } from "@/components/ProcessingNow";
import { ProsePageView } from "@/components/ProsePageView";
import { privacy } from "@/lib/content";

export const metadata: Metadata = { title: privacy.title };

export default function PrivacyPage() {
  return (
    <ProsePageView page={privacy}>
      {/* What this server, as configured now, sends to Google, if anything. */}
      <ProcessingNow />
    </ProsePageView>
  );
}
