import type { Metadata } from "next";

import { Bookmarks } from "@/components/Bookmarks";
import { strings } from "@/lib/strings";

export const metadata: Metadata = { title: strings.bookmarksHeading };

export default function BookmarksPage() {
  return <Bookmarks />;
}
