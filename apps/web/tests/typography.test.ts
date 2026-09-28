import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Sinhala sets the typography (see the head of globals.css, and the guide,
 * section 6). Vowel signs stack above and below the letter, so a Latin line
 * height clips them into the next line, and negative tracking pulls them into
 * the next letter. Both have shipped here before, in a later layer of the
 * stylesheet that overrode the rules above it. This reads every declaration.
 */

// Vitest runs from apps/web.
const css = readFileSync(resolve("src/app/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function declarations(property: string): string[] {
  const pattern = new RegExp(String.raw`(?:^|[;{\s])${property}:\s*([^;}]+)`, "g");
  return [...css.matchAll(pattern)].map((m) => m[1]!.trim());
}

describe("typography for Sinhala", () => {
  it("never sets a line height below 1.5", () => {
    const tooTight = declarations("line-height").filter((value) => {
      if (/^var\(--leading-(tight|normal|reading)\)$/.test(value)) return false;
      const number = Number(value);
      return !(Number.isFinite(number) && number >= 1.5);
    });
    expect(tooTight).toEqual([]);
  });

  it("keeps the reading leading at 1.9 or more", () => {
    const reading = /--leading-reading:\s*([\d.]+)/.exec(css)?.[1];
    expect(Number(reading)).toBeGreaterThanOrEqual(1.9);
  });

  it("never tracks letters closer together", () => {
    expect(declarations("letter-spacing").filter((value) => value.startsWith("-"))).toEqual([]);
  });

  it("sizes headings in rem-based steps, so text zoom enlarges them", () => {
    // A size of vw alone does not grow with zoom (WCAG 1.4.4).
    const vwOnly = declarations("font-size").filter(
      (value) => /vw/.test(value) && !/rem/.test(value.replace(/clamp\(|\)/g, "")),
    );
    expect(vwOnly).toEqual([]);
    const middles = declarations("font-size")
      .filter((value) => value.startsWith("clamp("))
      .map((value) => value.slice(6, -1).split(",")[1]!.trim())
      .filter((middle) => /vw/.test(middle) && !/rem/.test(middle));
    expect(middles).toEqual([]);
  });
});
