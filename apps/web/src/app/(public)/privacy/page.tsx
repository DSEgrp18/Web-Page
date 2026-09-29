import type { Metadata } from "next";

import { ProcessingNow } from "@/components/ProcessingNow";
import { ProsePageView } from "@/components/ProsePageView";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: contentFor(await getLocale()).privacy.title };
}

export default async function PrivacyPage() {
  const locale = await getLocale();
  return (
    <ProsePageView page={contentFor(locale).privacy} strings={stringsFor(locale)}>
      {/* What this server, as configured now, sends to Google, if anything. */}
      <ProcessingNow />
    </ProsePageView>
  );
}
