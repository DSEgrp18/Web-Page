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
  prefixes normalised away; a per-font verdict on all that font's text on a
  page, for fonts whose names identify nothing; and a script guard so text
  this reader has no voice for is shown but never spoken.
- Content drawn outside the printed page area left out, since it is invisible
  to a sighted reader and must not be narrated to anyone else.
- Printed page labels from `/PageLabels`, so a citation to "page vi" means what
  the reader would see.
- Selective page extraction, so the first requested section can be produced
  before the rest of the book.
- Multi-column reading order flagged as uncertain.

- **FM-Abhaya conversion**, decoding legacy spans into Sinhala Unicode using
  the vendored mapping table.

## What is not implemented, and is announced rather than faked

- **Legacy families other than FM-Abhaya.** It is the only one with a mapping
  table. A wrong mapping does not fail loudly — it produces fluent Sinhala
  saying something the author never wrote — so the rest are withheld.
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
src/sinhala_documents/legacy_fm_abhaya.py  FM-Abhaya to Sinhala Unicode conversion.
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

## What a real book showed

The first real document run through this was a 168-page Grade 11 Sinhala
history textbook. It is set almost entirely in FM-Abhaya: **244,126 of its
248,055 characters are legacy**. Without font identification, a reader would
have narrated a quarter of a million characters of Latin gibberish, confidently,
to someone who could not see the page.

Three defects only a real book could have surfaced:

| | |
| --- | --- |
| **Off-page content** | One page drew 3,322 of its 3,792 characters outside the sheet — a whole duplicated article, invisible when rendered, which extraction interleaved character by character with the four visible lines. |
| **A font that identifies nothing** | 3,293 characters were set in `KQAHVM+CIDFont+F2`. No name to match, no Sinhala in the output, and a per-line non-ASCII rate below any usable threshold. All of it was being narrated. |
| **The wrong signal** | FM-Abhaya's non-ASCII rate is 0.073 — *below* the 0.08 threshold meant to catch it. A non-ASCII test alone would have missed the entire book. |

The signal that works is **interior capitals**: legacy fonts map glyphs to Latin
code points without regard to case, so decoded text is full of words like
`wOHdmk` and `fomd¾;fïka;=j`. Aggregated per font, on that book:

| font | interior capitals | non-ASCII |
| --- | ---: | ---: |
| FM-Abhaya (legacy) | 0.202 | 0.073 |
| FM-Abhaya Bold (legacy) | 0.221 | 0.068 |
| CIDFont+F2 (legacy, unnamed) | 0.191 | 0.056 |
| Times New Roman (real English) | 0.083 | 0.016 |
| English control sentences | 0.033 | 0.000 |

Aggregating per **font per page** is what makes this reliable — `NASA and the
UNESCO report` scores 0.167 on its own but 0.033 inside a paragraph, and it is
the paragraph that describes the font. Per page rather than per document so
that a page is classified the same whether it was requested alone or as part of
the whole book.

Readable output on that book went from 6,798 characters, essentially all of it
gibberish, to **559 characters — all genuine**: the English translation of the
presentation inscription, acronyms in the glossary, and the printed roman page
numbers.

## Converting FM-Abhaya

With the converter in place, that book yields **246,097 readable characters —
92.8% of everything on its pages**, as real Sinhala:

> හිට්ලර් 1933 දී බලයට පත් වූයේ එරට පාර්ලිමේන්තුවේ තවත් මන්ත්‍රීවරුන්ගේ සහය ලබාගනිමිනි.

The algorithm is the table's own, documented in its header: two ordered passes,
each a longest-match-first left-to-right **scan**. Scanning rather than repeated
global replacement is the whole game — a scan never re-reads what it emitted,
and the table contains reordering rules whose output would otherwise be
rewritten by the next rule.

All six supplied examples convert character-for-character.

### One addition beyond the table

Sinhala writes several vowel signs to the *left* of the consonant they modify,
and legacy fonts store them that way; Unicode stores them after. The table
resolves this with combined entries — `fod` → `දො` — but only for the spellings
it lists. The same word set with the variant code point `Þ` has no `fÞ` entry,
so the sign is converted separately and left stranded in front, producing
`ෙදාරේසාමි` instead of `දොරේසාමි`. This affected 316 of 5,435 spans.

The repair moves a mark back after its consonant, then composes with NFC (`ො` is
canonically `ෙ` followed by `ා`). It is deliberately narrow: it only touches
marks that are **already malformed** — no consonant, mark or ZWJ before them —
so correctly converted text cannot be disturbed. In `දෙර` the sign already
follows its consonant and is left alone, even though another consonant follows
it.

This goes beyond the table's documented passes, so it is counted in
`ConversionReport.repaired_marks` and **wants a native speaker's confirmation**
on real pages.

### What the checks can and cannot tell you

`convert_with_report` measures unmapped Latin and invalid combining sequences.
These find *malformed* output. They cannot tell you the conversion is **right**,
and they cannot tell you the input was FM-Abhaya in the first place — ordinary
English put through the table sometimes converts to orthographically legal
Sinhala. The font name is the gate. CLAUDE.md says orthography checks cannot
establish transcription accuracy; that is what it means in practice.

## Sinhala only

The reader serves Sinhala and has a Sinhala voice. Sri Lankan textbooks are
trilingual, and this one sets Tamil in legacy fonts too, but no catalogue of
Tamil fonts is kept here — that would promise support this reader does not
offer.

Such text is still never narrated. `is_unreadable_script` withholds anything
that carries no Sinhala and is overwhelmingly outside ASCII, without naming a
language: the answer is the same for every script this reader has no voice for.
It is shown on the page, and not spoken.

## Not yet verified

One book is not a corpus. The thresholds above are measured rather than
borrowed, but measured on a single document, and CLAUDE.md is explicit that they
must be calibrated against ground truth rather than adopted as proven defaults.
Re-measure as more real documents arrive.

Still untested against real inputs: a **scanned** book, a Unicode Sinhala book
(this one had almost none), and a genuinely multi-column layout. That book also
declares no `/PageLabels`, so printed page numbers were reported as absent —
correctly, since they exist only in the page footers, which is a job for the
header and footer increment.
