import type { Metadata } from "next";
import Link from "next/link";

import { PublicFrame } from "@/components/PublicFrame";
import { strings } from "@/lib/strings";

// Spelled out: like the landing page, this shares the root layout's segment,
// where the `%s — ස්වර` template does not apply.
export const metadata: Metadata = {
  title: { absolute: `${strings.errorNotFound} — ${strings.appName}` },
};

/**
 * Any address with nothing at it.
 *
 * In the site's own frame and language, with its navigation, rather than
 * Next's default: an unbranded English "404" with no way back is a dead end,
 * and a screen reader announces it with the wrong voice.
 */
export default function NotFound() {
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
