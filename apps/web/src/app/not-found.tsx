import type { Metadata } from "next";
import Link from "next/link";

import { PublicFrame } from "@/components/PublicFrame";
import { getStrings } from "@/lib/i18n.server";

// Spelled out: like the landing page, this shares the root layout's segment,
// where the `%s — ස්වර` template does not apply.
export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: { absolute: `${strings.errorNotFound} — ${strings.appName}` } };
}

/**
 * Any address with nothing at it.
 *
 * In the site's own frame and language, with its navigation, rather than
 * Next's default: an unbranded English "404" with no way back is a dead end,
 * and a screen reader announces it with the wrong voice.
 */
export default async function NotFound() {
  const strings = await getStrings();
  return (
    <PublicFrame>
      <div className="prose-page">
        <h1>{strings.errorNotFound}</h1>
        <p>
          <Link className="btn btn-primary" href="/library">
            {strings.libraryHeading}
          </Link>
        </p>
      </div>
    </PublicFrame>
  );
}
