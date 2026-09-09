# Sinhala Accessible Reader

A Sinhala document reader and document-grounded study assistant for blind and
low-vision readers and students.

The intended experience is simple: upload a Sinhala PDF, choose a page or
chapter, listen, pause, and resume — entirely by keyboard and screen reader.
Beyond reading, students can ask questions about the document they uploaded and
hear answers that cite the pages they came from.

## Status

**Early setup. There is no running application yet.**

This repository currently contains project specifications, vendored legacy-font
data, and repository tooling. Nothing here synthesises speech or reads a PDF
today. The sections below describe what is planned; they are not a description
of working software, and this README will be corrected as capabilities land
rather than written ahead of them.

| Area | State |
| --- | --- |
| Repository governance, CI, branch protection | In place |
| Legacy FM-Abhaya font data (vendored, verified) | In place, decoder not implemented |
| Sinhala TTS text front end | Vendored and tested; three defects documented |
| Sinhala XTTS inference | Not started. Procedure, settings, and limits recorded in [the manifest](docs/model-inference-manifest.md); no audio generated yet |
| Document upload, extraction, and playback | Not started |
| Retrieval and document question answering | Not started |

## Planned scope

**Read mode** narrates the text extracted from the document. It is never
rewritten by a language model. **Study mode** answers questions using passages
retrieved from the document, labels its output as AI-generated, cites the pages
it used, and abstains when the document does not support an answer.

The first release targets digital Sinhala PDFs and pasted text, sentence-level
narration with page and chapter navigation, bookmarks and saved progress,
cached and downloadable audio, and document questions with page citations.
Scanned PDFs with Sinhala OCR, a correction workflow, and grounded summaries
follow.

Accessibility targets WCAG 2.2 AA and is validated with people who use assistive
technology. If a core task cannot be completed with NVDA or TalkBack, that is a
release blocker.

## Planned architecture

A Next.js progressive web app over a FastAPI backend, with Celery and Redis for
background jobs, PostgreSQL with pgvector for data and retrieval, private
S3-compatible object storage, and a separate GPU worker wrapping the existing
Sinhala XTTS model for inference only.

There is no training pipeline in this project. The model is already trained and
is integrated for inference.

## Model assets

The Sinhala XTTS bundle is **not** in this repository and cannot be obtained
from it. It is delivered out of band by the project owner and located through
configuration at runtime. Checkpoints, speaker reference audio, uploaded
documents, and generated audio never enter Git; CI enforces this.

The licence position of the underlying XTTS-v2 weights under CPML, including its
non-commercial restrictions, is unresolved and must be settled before any
commercial deployment.

## Repository layout

```text
services/tts/        Sinhala XTTS text front end, segmentation, synthesis adapter
services/worker/     PDF extraction, FM-Abhaya decoding, and the reading pipeline
services/api/        Reader API: upload, segments, audio, progress
data/legacy_fonts/   Vendored FM-Abhaya to Unicode mapping (MIT, hash-verified)
docs/                Inference manifest and repository setup evidence
scripts/             Repository verification scripts
.github/             CI, code owners, issue and pull request templates
CLAUDE.md            Governing project specification
CONTRIBUTING.md      How we work: branches, reviews, definition of done
CODE_OF_CONDUCT.md   Expected conduct and how to report a concern
SECURITY.md          Vulnerability and private-data reporting
LICENSE              MIT licence for this repository's code
```

The remaining directories (`apps/web/`, `evaluation/`, `infra/`) are created by
the pull requests that introduce them.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, review requirements,
and the definition of done, and [CLAUDE.md](CLAUDE.md) for the governing
specification. Participation is covered by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Licence

Three different sets of terms apply to three different things. Read this before
reusing any part of the project.

**The source code in this repository is MIT licensed.** See [LICENSE](LICENSE).
You may use, modify, and redistribute it, including commercially, with
attribution.

**The vendored legacy-font data is separately MIT licensed** by its upstream
authors (akuruAI/Pandukabhaya, derived from UCSC Language Technology Research
Laboratory research). See [data/legacy_fonts/LICENSE](data/legacy_fonts/LICENSE)
and the provenance notes in
[data/legacy_fonts/README.md](data/legacy_fonts/README.md).

**The Sinhala XTTS model is not covered by the MIT licence above, and is not
distributed here.** The MIT licence applies to this repository's code only. It
grants no rights whatsoever to the model weights, which live outside Git and are
supplied out of band.

That matters, because the underlying XTTS-v2 weights are published under the
Coqui Public Model Licence (CPML), which **restricts use to non-commercial
purposes**. Fine-tuning a model does not automatically remove the terms attached
to the weights it was derived from. Whether and how CPML applies to the
fine-tuned Sinhala checkpoint used by this project **has not yet been resolved**,
and must be settled before any commercial deployment.

Permission to use the supplied speaker reference audio must also be confirmed
before public release.

In short: the code is free to reuse; running it with this project's voice is not
yet cleared for commercial use. If you intend to deploy commercially, resolve the
model licensing question first — do not treat the MIT licence on this repository
as covering it.
