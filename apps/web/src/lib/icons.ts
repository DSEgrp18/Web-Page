import type { Metadata } from "next";

/**
 * A flat book with the gold ribbon, drawn for small sizes: the illustrated
 * book it replaces blurred to nothing in a 16 px tab, and its transparency
 * left a white halo on a dark tab bar. The SVG serves browsers that take it;
 * 16 px has its own drawing, with a heavier book, because scaling the large
 * one down loses the ribbon. The Apple icon is square and opaque: iOS rounds
 * the corners itself, and fills transparency with black.
 */
export const ICONS = {
  icon: [
    { url: "/brand/icon.svg", type: "image/svg+xml" },
    { url: "/brand/icon-16.png", sizes: "16x16", type: "image/png" },
    { url: "/brand/icon-32.png", sizes: "32x32", type: "image/png" },
    { url: "/brand/icon-192.png", sizes: "192x192", type: "image/png" },
    { url: "/brand/icon-512.png", sizes: "512x512", type: "image/png" },
  ],
  apple: [{ url: "/brand/apple-icon.png", sizes: "180x180", type: "image/png" }],
} satisfies Metadata["icons"];
