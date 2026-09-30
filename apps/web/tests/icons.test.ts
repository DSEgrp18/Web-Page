/**
 * The icons the layout declares exist, and are the size they claim.
 *
 * A browser that fetches a missing icon shows a blank tab; one whose declared
 * size is wrong picks the wrong file and scales it into a blur, which is the
 * defect the new icon exists to fix.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { ICONS } from "../src/lib/icons";

const PUBLIC = join(__dirname, "../public");

/** Width and height from a PNG's IHDR chunk. */
function pngSize(path: string): string {
  const bytes = readFileSync(path);
  expect(bytes.subarray(1, 4).toString("latin1"), path).toBe("PNG");
  return `${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`;
}

describe("the icons", () => {
  const all = [...ICONS.icon, ...ICONS.apple];

  it.each(all.map((icon) => [icon.url, icon] as const))("%s exists as declared", (_url, icon) => {
    const path = join(PUBLIC, icon.url);
    if (icon.type === "image/png") {
      expect(pngSize(path)).toBe((icon as { sizes: string }).sizes);
    } else {
      expect(readFileSync(path, "utf8")).toMatch(/^<svg [^>]*viewBox="0 0 512 512"/);
    }
  });

  it("gives Apple an opaque, square icon", () => {
    // Colour type 2 is RGB without alpha: iOS paints transparency black.
    const bytes = readFileSync(join(PUBLIC, ICONS.apple[0]!.url));
    expect(bytes[25]).toBe(2);
  });
});
