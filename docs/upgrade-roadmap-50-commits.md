# Swara: 50-commit product upgrade roadmap

This roadmap takes the current working reader to a credible release candidate. Each numbered
item is intended to be one reviewable commit with its own tests. A phase is complete only when
its end-to-end flow passes CI and a browser check; commits must not claim manual or model
results that were not measured.

## Phase 1 — Baseline and UI quality gates

1. **Remove current framework warnings.** Update `next.config.mjs` for Next 16 and keep a clean
   development and production build.
2. **Expand the Playwright smoke path.** Cover identity, library, upload, document opening,
   sentence selection, pause, resume, and return to the library.
3. **Add mobile browser coverage.** Run the core flow at a small Android viewport and assert
   that the PDF/text tabs and player remain usable.
4. **Add browser accessibility checks.** Run axe in Chromium on the library, upload dialog,
   reader, settings, bookmarks, and study drawer.
5. **Add screenshot regression baselines.** Record light, dark, desktop, mobile, empty, loading,
   and error states, with an intentional review process for changed images.

**Phase gate:** CI is quiet, the core journey is covered in Chromium, and visual changes are
reviewable rather than subjective.

