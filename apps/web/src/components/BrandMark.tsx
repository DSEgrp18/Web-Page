import Link from "next/link";

/**
 * The Swara mark: the roof over an open book, and ස්වර beside it, as the logo
 * draws them.
 *
 * Two images, one per theme, because the logo's blue is too dark to see on
 * the night palette: the dark copy lifts the blue and keeps the orange. CSS
 * shows the one that matches the theme, whether the reader's system chose it
 * or the reader did in Settings (`data-theme`), which a `<picture>` media
 * query cannot see.
 *
 * Plain `<img>` rather than `next/image`: a fixed-size mark in the masthead of
 * every screen gains nothing from the optimiser's extra request. Explicit
 * `width`/`height` reserve the box, so the header does not jump when it lands.
 *
 * The images are decorative; the link's name is the word itself, in Sinhala,
 * marked as Sinhala for a screen reader speaking English around it. It is the
 * same name in every interface language: it is the name, not a word to
 * translate.
 */
export function BrandMark({ href = "/" }: { href?: string }) {
  return (
    <Link className="brand" href={href}>
      <img
        className="brand-lockup brand-lockup-light"
        src="/brand/swara-lockup.webp"
        alt=""
        width={528}
        height={140}
        // Above the fold on every screen; lazy-loading only makes it late.
        loading="eager"
        decoding="async"
      />
      <img
        className="brand-lockup brand-lockup-dark"
        src="/brand/swara-lockup-dark.webp"
        alt=""
        width={528}
        height={140}
        loading="eager"
        decoding="async"
      />
      <span className="visually-hidden" lang="si">
        ස්වර
      </span>
    </Link>
  );
}
