import type { ReactNode } from "react";

/**
 * A public page with a photograph behind the article.
 *
 * The picture is decoration: it is hidden from assistive technology, and the
 * words sit on the solid card, never on the photograph.
 */
export function GuideFrame({
  src,
  srcSet,
  width,
  height,
  focus = "center 42%",
  children,
}: {
  src: string;
  srcSet: string;
  width: number;
  height: number;
  /** Where the visible band of the photograph should sit. */
  focus?: string;
  children: ReactNode;
}) {
  return (
    <div className="guide">
      <figure className="guide-photo" aria-hidden="true">
        <img
          src={src}
          srcSet={srcSet}
          sizes="(max-width: 92rem) 100vw, 92rem"
          alt=""
          width={width}
          height={height}
          fetchPriority="high"
          decoding="async"
          style={{ objectPosition: focus }}
        />
      </figure>
      <div className="guide-sheet">{children}</div>
    </div>
  );
}
