import type { Metadata } from "next";

import { ProsePageView } from "@/components/ProsePageView";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: contentFor(await getLocale()).howItWorks.title };
}

export default async function Page() {
  const locale = await getLocale();
  return <ProsePageView page={contentFor(locale).howItWorks} strings={stringsFor(locale)} />;
}
