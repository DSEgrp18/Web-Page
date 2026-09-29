import type { Metadata } from "next";

import { Bookmarks } from "@/components/Bookmarks";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.bookmarksHeading };
}

export default function BookmarksPage() {
  return <Bookmarks />;
}
