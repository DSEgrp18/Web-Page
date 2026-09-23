import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Contrast, measured from the tokens rather than asserted in a comment.
 *
 * Every colour the page paints is a token in globals.css (verify-css makes
 * that so), so the pairs the stylesheet actually uses can be checked here, in
 * both themes, with the WCAG 2.2 formula. Browser axe checks the rendered
 * pages as well; this catches a token change before anything renders, and
 * names the pair that broke.
 *
 * The pairs come from the stylesheet: which `color` sits on which
 * `background`, plus the surfaces a colour inherits onto. Add a pair here when
 * a rule puts a token on a new surface.
 */

// Vitest runs from apps/web.
const css = readFileSync(resolve("src/app/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

type Theme = Record<string, string>;

function tokens(pattern: RegExp): Theme {
  const block = css.match(pattern)?.[1];
  if (!block) throw new Error(`no token block matches ${pattern}`);
  return Object.fromEntries(
    [...block.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1], m[2]]),
  );
}

const light = tokens(/:root\s*\{([^}]*)\}/);
const darkByPreference = tokens(/:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/);
const darkByChoice = tokens(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/);
const themes: [string, Theme][] = [
  ["light", light],
  ["dark", { ...light, ...darkByChoice }],
];

/** WCAG 2.2 relative luminance of a `#rrggbb` colour. */
function luminance(hex: string): number {
  const [r = 0, g = 0, b = 0] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** `color-mix(in srgb, top N%, transparent)` painted over `under`. */
function over(top: string, alpha: number, under: string): string {
  const channel = (hex: string, i: number) => parseInt(hex.slice(i, i + 2), 16);
  const mixed = [1, 3, 5].map((i) =>
    Math.round(channel(top, i) * alpha + channel(under, i) * (1 - alpha)),
  );
  return `#${mixed.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function ratio(a: string, b: string): number {
  const hi = Math.max(luminance(a), luminance(b));
  const lo = Math.min(luminance(a), luminance(b));
  return (hi + 0.05) / (lo + 0.05);
}

/** A token's colour, or a failure naming the token that is not a `#rrggbb`. */
function colour(theme: Theme, name: string): string {
  const value = theme[name];
  if (!value) throw new Error(`${name} is not a #rrggbb token in this theme`);
  return value;
}

const SURFACES = ["--paper", "--panel", "--panel-sunken"];
const TEXT = 4.5; // 1.4.3, normal-size text
const NON_TEXT = 3; // 1.4.11, control boundaries and the focus ring

const pairs: [string, string, number][] = [
  // Text that inherits onto any surface.
  ...["--ink", "--ink-muted", "--green", "--green-deep", "--bad-ink"].flatMap((ink) =>
    SURFACES.map((surface): [string, string, number] => [ink, surface, TEXT]),
  ),
  // The current sentence, the selected nav link and pressed tools.
  ["--ink", "--green-wash", TEXT],
  ["--ink-muted", "--green-wash", TEXT],
  ["--green-deep", "--green-wash", TEXT],
  // Primary buttons, the skip link and selected tabs, at rest and hovered.
  ["--ink-on-green", "--green", TEXT],
  ["--ink-on-green", "--green-deep", TEXT],
  ["--paper", "--green-deep", TEXT],
  // Pills, notices and the player warning: status ink, and body ink, on washes.
  ...["ok", "warn", "bad"].flatMap((s): [string, string, number][] => [
    [`--${s}-ink`, `--${s}-wash`, TEXT],
    ["--ink", `--${s}-wash`, TEXT],
    ["--ink-muted", `--${s}-wash`, TEXT],
  ]),
  // Control edges and the 3px focus ring, on everything they sit on.
  ...[...SURFACES, "--green-wash"].flatMap((surface): [string, string, number][] => [
    ["--edge", surface, NON_TEXT],
    ["--green", surface, NON_TEXT],
  ]),
];

describe("token contrast", () => {
  it("defines the dark theme the same way for the preference and the choice", () => {
    // Two copies of one palette: an edit to one alone makes the theme depend
    // on how dark mode was reached.
    expect(darkByPreference).toEqual(darkByChoice);
  });

  describe.each(themes)("the %s theme", (_name, theme) => {
    it.each(pairs)("%s on %s", (fg, bg, minimum) => {
      expect(ratio(colour(theme, fg), colour(theme, bg))).toBeGreaterThanOrEqual(minimum);
    });
  });

  // The body's glow: 9% of --green over --paper at the top of every page.
  // The browser run removes gradients before measuring, so this is where the
  // brightest point of the glow is checked.
  describe.each(themes)("text on the page glow, %s theme", (_name, theme) => {
    const glow = over(colour(theme, "--green"), 0.09, colour(theme, "--paper"));
    it.each(["--ink", "--ink-muted", "--green", "--green-deep", "--bad-ink"])("%s", (ink) => {
      expect(ratio(colour(theme, ink), glow)).toBeGreaterThanOrEqual(TEXT);
    });
  });

  it("measures known values correctly", () => {
    expect(ratio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(ratio("#767676", "#ffffff")).toBeCloseTo(4.54, 2);
    expect(over("#ffffff", 0.5, "#000000")).toBe("#808080");
  });
});
