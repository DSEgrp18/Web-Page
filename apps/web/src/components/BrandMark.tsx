import Link from "next/link";

import { strings } from "@/lib/strings";

/**
 * The Swara mark: the open book, and ස්වර beside it.
 *
 * Plain `<img>` rather than `next/image`. The optimiser earns its keep on
 * user-uploaded photographs of unknown size; this is a 12 KiB WebP at a fixed
 * size in the masthead of every screen, and routing it through a server
 * endpoint would add a request without changing a byte that reaches the page.
 * Explicit `width`/`height` do the one thing that actually matters here —
 * reserve the box, so the header does not jump when the image lands.
 *
 * The image is decorative: the wordmark beside it already says "ස්වර", and a
 * screen reader announcing the book twice is noise. So `alt=""`, and the link's
 * accessible name comes from the text.
 */
export function BrandMark({ href = "/" }: { href?: string }) {
  return (
    <Link className="brand" href={href}>
      <img
        className="brand-mark"
        src="/brand/swara-mark.webp"
        alt=""
        width={168}
        height={108}
        // The masthead mark is above the fold on every screen; lazy-loading it
        // only guarantees it arrives late.
        loading="eager"
        decoding="async"
      />
      <span>
        <span className="brand-word">{strings.appName}</span>
        <span className="brand-latin">{strings.appNameLatin}</span>
      </span>
    </Link>
  );
}
