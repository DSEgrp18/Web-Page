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

## Phase 2 — Application shell and navigation

6. **Refine the desktop shell.** Standardise header height, content measure, spacing, active
   navigation, and page titles using existing design tokens.
7. **Refine mobile navigation.** Add a compact navigation pattern with correct focus order,
   current-page state, and 44-pixel touch targets.
8. **Add consistent breadcrumbs and back navigation.** Preserve the reader's last page and
   sentence when moving between reading, bookmarks, and study views.
9. **Build shared loading patterns.** Replace layout jumps with labelled skeletons and stable
   panel dimensions without announcing every loading tick.
10. **Complete designed error and empty states.** Implement issue #38 with recovery actions,
    useful Sinhala copy, and browser tests for offline, rejected, and not-ready responses.

**Phase gate:** every route has a coherent loading, success, empty, and recoverable error state.

## Phase 3 — Library and upload experience

11. **Add library search and sorting.** Search by title or filename and sort by recent,
    alphabetical, progress, and preparation status.
12. **Improve book cards.** Show meaningful title, page count, progress, last read time, and
    status while keeping actions unambiguous to screen readers.
13. **Add multi-format, multi-file upload.** Keep the native file control, add a visible drop
    target, accept PDF, DOCX, PNG, and JPEG files, validate type and size before upload, and
    report the result of each file without hiding partial failures.
14. **Create detailed preparation progress.** Present upload, extraction, OCR, segmentation,
    indexing, and audio readiness as honest server states with retry and cancellation.
15. **Add bulk library management.** Support selection, deletion confirmation, and accessible
    batch status without weakening ownership checks.

**Phase gate:** a new user can add, understand, find, rename, resume, and delete books without
guessing what the system is doing.

The document pipeline for this phase includes native PDF text, DOCX paragraphs, and Sinhala OCR
for scanned PDF pages and standalone images. Original PDF and image previews stay beside the
accessible extracted text; DOCX keeps a download of the original and clearly states that its
page layout is not reproduced in the browser.

## Phase 4 — Reading workspace redesign

16. **Polish the responsive split view.** Improve resizing, panel collapse, persisted width,
    mobile tabs, and keyboard control at 200–400% zoom.
17. **Upgrade PDF viewing controls.** Add fit-width, fit-page, zoom, rotate, and clear page
    navigation while retaining extracted text as the accessible reading surface.
18. **Add thumbnail and chapter navigation.** Provide optional thumbnails and contents in a
    labelled side sheet with current-page and current-chapter state.
19. **Upgrade sentence and word inspection.** Add current-word selection, copy, pronunciation
    feedback, and return-to-current controls without requiring word timestamps for playback.
20. **Add document search.** Search extracted text, list results with page context, and navigate
    without autoplay or losing the current reading position.

**Phase gate:** sighted, low-vision, keyboard, and screen-reader users can navigate the same
document state through controls suited to them.

## Phase 5 — Player, voice, and offline listening

21. **Complete the player control design.** Implement issue #33 with native controls, clear
    labels, honest position, and scoped keyboard help.
22. **Expose voice warm-up state.** Implement issue #28 with readiness, queue position, retry,
    and cached-audio availability.
23. **Improve continuous playback.** Add bounded prefetch, deduplicate synthesis, recover from
    one failed segment, and prevent overlapping audio.
24. **Add evaluated voice selection.** Put XTTS and the adapted female VITS model behind the
    same adapter, label model provenance, and expose only voices that pass smoke tests.
25. **Add chapter download and offline playback.** Implement issue #32 with manifests,
    authorised files, progress, cancellation, storage limits, and removal controls.

**Phase gate:** listening remains responsive under cold, cached, interrupted, and offline
conditions, and the selected voice is never silently substituted.

## Phase 6 — Accessibility acceptance

26. **Complete native-speaker review.** Resolve issue #27 and record reviewer, date, changed
    strings, and terminology decisions.
27. **Run and fix the NVDA journey.** Resolve issue #25 for identity, upload, preparation,
    opening, navigation, playback, bookmarks, settings, and study mode.
28. **Run and fix the TalkBack journey.** Resolve issue #26 on a small Android device with
    touch exploration, virtual keyboard, and interrupted connectivity.
29. **Validate reflow and visual accessibility.** Test 400% zoom, high contrast, dark mode,
    reduced motion, focus visibility, and text scaling across every core route.
30. **Turn acceptance findings into regression tests.** Add focused tests for every fixed
    semantic, focus, announcement, target-size, and reflow defect.

**Phase gate:** no critical blocker remains in core tasks; the report contains real tester and
device evidence rather than automated claims standing in for assistive technology.

## Phase 7 — Document quality and correction

31. **Implement the FM-Abhaya converter.** Use the supplied ordered mapping, span-level font
    detection, provenance, and all supplied character-for-character cases.
32. **Create an OCR evaluation set.** Add permission-cleared scanned pages, human transcripts,
    CER/WER measurement, and error groups for letters, marks, numbers, and layout.
33. **Add extraction review UI.** Show native, legacy, and OCR provenance with page warnings and
    side-by-side source comparison.
34. **Add correction workflow.** Let authorised reviewers correct display/spoken text, create a
    new document version, invalidate derived audio/indexes, and retain an audit trail.
35. **Improve structure and reading order.** Handle columns, headings, captions, lists, tables,
    running furniture, and uncertain blocks with deterministic fallback.

**Phase gate:** document errors can be measured, found, corrected, versioned, and regenerated
without changing the words silently.

