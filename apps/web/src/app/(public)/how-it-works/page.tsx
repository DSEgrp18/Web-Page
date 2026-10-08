import type { Metadata } from "next";

import { GuideFrame } from "@/components/GuideFrame";
import { ProsePageView } from "@/components/ProsePageView";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: contentFor(await getLocale()).howItWorks.title };
}

export default async function Page() {
  const locale = await getLocale();
  return (
    <GuideFrame
      src="/images/reading-desk-1600.webp"
      srcSet="/images/reading-desk-800.webp 800w, /images/reading-desk-1600.webp 1600w"
      width={1600}
      height={1067}
    >
      <ProsePageView page={contentFor(locale).howItWorks} strings={stringsFor(locale)} />
    </GuideFrame>
  );
}
