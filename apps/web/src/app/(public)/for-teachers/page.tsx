import type { Metadata } from "next";

import { GuideFrame } from "@/components/GuideFrame";
import { ProsePageView } from "@/components/ProsePageView";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: contentFor(await getLocale()).forTeachers.title };
}

export default async function Page() {
  const locale = await getLocale();
  return (
    <GuideFrame
      src="/images/classroom-1600.webp"
      srcSet="/images/classroom-800.webp 800w, /images/classroom-1600.webp 1600w"
      width={1600}
      height={1067}
      focus="center 28%"
    >
      <ProsePageView page={contentFor(locale).forTeachers} strings={stringsFor(locale)} />
    </GuideFrame>
  );
}
