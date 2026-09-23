import type { Metadata } from "next";

import { Library } from "@/components/Library";
import { strings } from "@/lib/strings";

/**
 * Written out in full, unlike every other route's title. The root layout's
 * `%s — ස්වර` template applies only to *child* segments, and this page shares
 * the root's segment, so a plain string here would render as the heading alone,
 * with no product name. Found by reading the built HTML, not by a unit test.
 */
export const metadata: Metadata = {
  title: { absolute: `${strings.libraryHeading} — ${strings.appName}` },
};

export default function LibraryPage() {
  return <Library />;
}
