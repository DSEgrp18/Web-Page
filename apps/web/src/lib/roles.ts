/**
 * How a segment's role is announced.
 *
 * A sighted reader sees that a caption is a caption from its size and position.
 * Somebody listening has only what is said, so the role travels in the
 * accessible name — which is the whole point of having recovered it.
 *
 * Two roles are deliberately silent:
 *
 * - `paragraph`, because announcing "paragraph" before every sentence of a
 *   book is noise, and noise is what a screen-reader user is trying to escape.
 * - `unknown`, because it means nothing classified this page. It reads exactly
 *   as prose, so announcing it would report our uncertainty as if it were a
 *   property of the book.
 *
 * `running_head` and `page_number` never reach a reader: the pipeline keeps
 * their text and drops them from the narration, so they are absent here rather
 * than silent.
 */

import type { Segment } from "./types";
import { strings } from "./strings";

export function roleLabel(segment: Pick<Segment, "role" | "level">): string | null {
  switch (segment.role) {
    case "heading":
      // The depth is part of it. "Heading" alone flattens a contents tree into
      // a list of equals, and a reader navigating by heading needs to know
      // whether they have moved to a new chapter or a subsection of this one.
      return segment.level
        ? `${strings.headingLevel(segment.level)} ${strings.roleHeading}`
        : strings.roleHeading;
    case "caption":
      return strings.roleCaption;
    case "contents_row":
      return strings.roleContentsRow;
    case "list_item":
      return strings.roleListItem;
    case "table_cell":
      return strings.roleTableCell;
    case "address":
      return strings.roleAddress;
    default:
      return null;
  }
}
