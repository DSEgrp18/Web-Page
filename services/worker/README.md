# services/worker

Document extraction: turning an uploaded PDF into text the reader is allowed to
speak, together with the provenance needed to justify that permission.

Right now this package handles **digital PDFs only** — files that already carry
text. Scanned pages are classified and reported, not recognised.

## The problem this package exists for

A Sinhala PDF can be text on the page and still be unreadable. Before Unicode
was usable on Sri Lankan desktops, Sinhala was typed in fonts that put Sinhala
glyphs at Latin code points. A file made that way contains no Sinhala at all: a
text extractor faithfully returns the Latin characters that are really there,
and they mean nothing.

Nothing about that output is malformed. It is not empty, not corrupt, and not
flagged by any check that asks whether extraction "worked". Handed on without
comment, the reader narrates confident gibberish, and the person listening — who
cannot see the page — has no way to tell.

So extraction here reports two independent things about every span of text:

| | |
| --- | --- |
| **How it was obtained** | `native`, `legacy`, `ocr`, `none` |
| **Whether it can be trusted** | `accepted`, `needs_review`, `undecodable` |

They are kept apart deliberately. Native extraction produces garbage from a
legacy font; OCR produces clean text from a good scan. Collapsing both into one
confidence score would destroy the only distinction that decides whether to
speak.

Text marked `undecodable` is withheld from narration but **kept on the page with
its geometry**, so the interface can say that part of this page could not be
read rather than presenting it as blank.

## What is implemented

- Upload validation: header, size, page count, encryption, with reasons fit to
  show a reader.
- Per-page classification — text, image, mixed, or blank — decided per page,
  because real books mix typeset chapters with scanned diagrams.
- Line and span assembly with font names, sizes, and bounding boxes preserved.
- Word boundaries reconstructed from geometry, not only from space characters,
  since many PDFs contain none.
- Legacy Sinhala font identification from span font metadata, with subset
  prefixes normalised away, plus a weaker fallback on the shape of the text.
- Printed page labels from `/PageLabels`, so a citation to "page vi" means what
  the reader would see.
- Selective page extraction, so the first requested section can be produced
  before the rest of the book.
- Multi-column reading order flagged as uncertain.

## What is not implemented, and is announced rather than faked

- **Legacy font conversion.** The FM-Abhaya mapping is vendored in
  `data/legacy_fonts/` but the converter is not written. Legacy spans are
  identified and withheld. A wrong mapping does not fail loudly — it produces
  fluent Sinhala saying something the author never wrote — so guessing is worse
  than refusing.
- **OCR.** Image-only pages are classified and reported.
- **Column reordering.** Detected and declared uncertain, not repaired.
- **Header and footer removal.** Needs the whole document and its own tests,
  including a repeated story refrain that must survive.

## Running the checks

From this directory, with Python 3.12 or newer:

```bash
python -m pip install "pdfplumber>=0.11.4" "pytest>=8" "ruff==0.15.20"
python -m pytest
ruff check .
ruff format --check .
```

No install step is needed: `pyproject.toml` puts `src` and `tests` on the path
directly. On Windows, set `PYTHONIOENCODING=utf-8` first or the console cannot
print Sinhala test output.

## Test fixtures contain no PDFs

`scripts/verify-repo-hygiene.sh` blocks `*.pdf` from ever being tracked, because
uploaded books and scanned private documents are the most expensive thing this
public repository could leak. Committing "harmless" samples would be the first
crack in that rule.

So `tests/pdf_fixtures.py` writes PDFs in memory instead. It emits Sinhala text
through a Type0 font whose `/ToUnicode` map declares what each glyph code means
— pdfminer reads that map and never looks at glyph outlines, so any code point
can be produced without embedding or licensing a real font. The same mechanism
produces a page that claims to be set in `FMAbhaya` and emits the Latin
characters such a file really contains, which is the only honest way to test the
case this package exists for.

## Layout

```text
src/sinhala_documents/model.py         Extraction types: method, quality, geometry.
src/sinhala_documents/validation.py    Cheap checks before an untrusted file is parsed.
src/sinhala_documents/pdf_extract.py   Native PDF text, lines, spans, page classification.
src/sinhala_documents/fonts.py         Legacy Sinhala font identification.
src/sinhala_documents/page_labels.py   Printed page numbers from /PageLabels.
src/sinhala_documents/layout.py        Multi-column reading-order suspicion.
tests/pdf_fixtures.py                  In-memory PDF writer. No binaries are committed.
```

## Why pdfplumber

It exposes per-character font names and geometry, which legacy-font
identification and page-traceable sentences both require; an extractor that
returns only a string can do neither. It is MIT, as is pdfminer.six underneath
it. PyMuPDF is faster and also exposes spans, but it is AGPL-3.0 unless
separately licensed, and this project already carries one unresolved licence
question in the XTTS weights.

## Not yet verified

Everything here is tested against generated PDFs, which are correct by
construction and therefore easier than real ones. It has **not** been run
against a real Sinhala book, a real legacy-font document, or a real scan. The
thresholds in `fonts.py` and `layout.py` are reasoned, not calibrated against
ground truth, and CLAUDE.md is explicit that a reference project's numbers must
not be adopted as proven defaults. Treat them as starting points to measure.
