import type { Metadata } from "next";

import { GuideFrame } from "@/components/GuideFrame";
import { ProsePageView } from "@/components/ProsePageView";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: contentFor(await getLocale()).help.title };
}

export default async function Page() {
  const locale = await getLocale();
  return (
    <GuideFrame
      src="/images/student-laptop-1400.webp"
      srcSet="/images/student-laptop-700.webp 700w, /images/student-laptop-1400.webp 1400w"
      width={1400}
      height={982}
      focus="center 22%"
    >
      <ProsePageView page={contentFor(locale).help} strings={stringsFor(locale)} report />
    </GuideFrame>
  );
}
