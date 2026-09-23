# Sinhala Accessible Reader — Project Instructions

## Purpose and current state

Build a shippable, accessible Sinhala study platform for blind and low-vision readers and students. A student can listen to a textbook, ask about it, practise on it, and track their progress, independently. A teacher can prepare a book once for a whole class. The learning loop is **Listen → Understand → Practise → Track**.

The Sinhala XTTS model is already trained. Integrate the existing model for inference only. Do not introduce model training, fine-tuning, dataset collection for training, or automatic retraining unless explicitly requested.

The reader works end to end: extraction with FM-Abhaya decoding and OCR fallback, sentence narration, bookmarks, progress, chapters, and cited study answers with abstention. The phased plan for the rest, with the reasons behind each decision, is [`docs/product-plan.md`](docs/product-plan.md). Where this file states a rule, this file governs; where it describes direction, the plan holds the detail. Inspect the repository before making changes and update both as decisions become concrete.

## Product scope

The core experience is: upload a Sinhala PDF, select a page or chapter, listen, pause, and resume. After this works reliably, add scanned PDFs and questions answered from the uploaded document.

### Initial release

- Digital Sinhala PDF upload and pasted-text reading.
- Sentence-level narration, page/chapter navigation, playback speed, bookmarks, and saved progress.
- Accessible keyboard and screen-reader operation.
- Incremental audio generation and reuse of cached audio.
- Downloadable generated chapters for offline listening.
- Sinhala document questions and spoken answers with page citations.
- Private documents and authorization enforced throughout processing and retrieval.
- Operational monitoring, predictable failure handling, and reproducible deployment.

### Study platform scope

Agreed in [`docs/product-plan.md`](docs/product-plan.md), in phase order:

- A public portal and real accounts: public pages, sign-in, registration, and recovery without email.
- A teacher class library: a teacher reviews a book's flagged pages, attests the right to share it, and publishes it to a class, with its audio rendered once for every member.
- Practice questions grounded in the document, under the verification rule below.
- Progress and spaced review, presented as text first.
- Scanned PDFs with Sinhala OCR and extraction-quality review, and a teacher correction workflow.

Later: clearly labelled summaries grounded in the document.

### Out of scope unless requested

- Training or fine-tuning TTS, ASR, embedding, or language models.
- Voice cloning, voice commands, and spoken-question recognition.
- Native mobile applications, billing, and unrestricted public book sharing. Sharing is class-limited only.
- Guaranteed interpretation of handwriting, complex equations, tables, or diagrams.
- Offline model inference. Offline listening uses previously generated audio.
- Kubernetes, excessive microservices, and unnecessary orchestration platforms.
- Agentic features beyond practice-question generation (see the agentic boundary below).

## Essential product behavior

Maintain two clearly distinguished modes:

1. **Read mode:** narrates the extracted and reviewed document text. Never silently rewrite it with an LLM.
2. **Study mode:** produces labelled AI-generated explanations supported by retrieved document passages.

Do not claim full document accessibility when illustrations, equations, or reading order have not been handled. Announce unsupported content and use reviewed descriptions where available.

### Structure may be inferred by a model; words may not

Read mode's rule governs **the words**, not the layout. A page is not prose: a
table of contents, a figure caption, a heading, an address, and a running header
are different kinds of thing, and flattening them into one stream produces both
mis-structured narration and incorrect number reading. A number cannot be read
correctly without knowing what contains it — `1.1` is a decimal in a sentence
and a section number in a heading, and `1764` is a year, not a quantity.

An LLM may therefore be used to determine **structure over text already
extracted**: block roles (heading and level, paragraph, caption, list item,
table cell, contents row, address, date), reading order, and block boundaries.
It must reference the extracted spans rather than emit prose.

This is permitted only because it is verifiable, and the verification is
mandatory, not advisory:

- Reassemble the model's output and compare it to the extraction it was given.
  It must match character for character, ignoring whitespace. **A single
  altered, invented, or dropped character rejects the whole page**, which then
  falls back to deterministic structure and is marked `needs_review`.
- Structure is provenance-bearing like any other extraction stage: record the
  provider, model, prompt version, and settings, and include them in the
  document version and in every affected cache key.
- Structure inference is optional and configurable. The deterministic path must
  remain and must stay correct enough to ship without a provider, because it is
  what runs when the provider is unavailable, unaffordable, or wrong.
- Sending a reader's document to an external model is external processing:
  disclose it, apply page and cost limits, and keep uploads out of provider
  training by configuration and contract.

What remains forbidden is unchanged and is the point of the rule: a model must
never supply, correct, complete, or smooth the words a reader hears as the
document. A sighted proofreader catches an invented date; a blind student
cannot.

### Generated questions: a model may write a question; it may never be the only judge of its answer

Practice questions are study-mode content, labelled with how they were made.
A fill-in-the-blank question is the book's own sentence with one term removed,
and may say so. A model-drafted question is never presented as the document's
words. A model may draft a question and its options, but it must cite a
numbered passage it was given and quote its evidence.

A deterministic verifier then decides, and it is mandatory, not advisory:

- The quote must appear verbatim, after normalisation, in the cited passage.
  Zero-width joiners are part of Sinhala words and are kept.
- The correct option must be supported by the quote. No distractor may be.
- The cited passage must be one that was sent, and must be on a page accepted
  for reading. A page that needs review, or that a teacher withheld, never
  grounds a question.
- **A single failed check discards the question.** It is never repaired.

A model's opinion, such as an independent re-answer, may reject a question but
never accept one. Questions reach a class only after a teacher approves them.
Record the generator, provider, model, prompt version, verifier version, and
framework version on every quiz, and mark quizzes stale when the document
version moves.

A deterministic generator that needs no provider (fill-in-the-blank from the
book's own sentences) must remain available and good enough to ship, for the
same reason the deterministic structure path must: it is what runs when the
provider is unavailable, unaffordable, or wrong. If generation fails, say so
and offer it as a choice. Never switch generators silently.

### The agentic boundary

LangGraph is used for **practice-question generation only**, because that loop
genuinely cycles (draft, verify, bounded revision). The single-pass study
answers do not use it, and no other feature does without a new decision
recorded in the product plan.

- It runs only in the Celery worker and is imported lazily. A test asserts that
  the API process never loads `langgraph` or `langchain_core`.
- Every run is bounded: revisions per question, total model calls, wall-clock
  time, and a recursion limit.
- It retrieves only over the authorised document's passages in scope. It has
  no tools, no web access, and no cross-document context. Document contents are
  untrusted evidence, never instructions.
- Model calls use the project's own transport, not framework model wrappers.
- Human review is a database status (`draft`, `approved`, `published`), never a
  paused graph, so approval is a queryable, audited fact that is deleted with
  the document.

## Proposed architecture

- Frontend: Next.js, React, and TypeScript progressive web app.
- API: Python FastAPI.
- Background jobs: Celery and Redis.
- Database: PostgreSQL with pgvector.
- Storage: private S3-compatible object storage for documents, model artifacts, and audio.
- Inference: separate GPU worker wrapping the supplied Sinhala TTS implementation.
- Retrieval: lexical and multilingual vector search, selected through evaluation.
- Answer generation: replaceable LLM adapter, selected through Sinhala evaluation.
- Practice questions: a deterministic generator by default, and a LangGraph generator in the worker only, both judged by one deterministic verifier.
- Sessions: an httpOnly cookie through a same-origin route handler in the web app, with CSRF and Fetch-Metadata checks.
- Packaging: Docker with pinned dependencies and compatible GPU runtime.
- CI: GitHub Actions for relevant checks and builds.
- Monitoring: structured logs and service metrics; add dashboards as needed.

Prefer one application backend with separate background workers. Keep provider-specific integrations behind small interfaces. Do not add frameworks merely to demonstrate technology usage.

Suggested repository layout:

```text
apps/web/                 Accessible reader UI
services/api/             Auth, documents, playback, questions
services/worker/          Extraction, indexing, audio jobs
services/tts/             Model adapter and inference runtime
packages/contracts/      Shared API contracts where useful
evaluation/              Fixed evaluation sets and scripts
infra/                   Containers and deployment configuration
docs/                    Architecture, research protocol, runbooks
```

Adapt this structure if existing code establishes a different convention.

Define small typed interfaces for extraction, OCR, and TTS, with implementations selected at the composition root. Keep Sinhala text transformations framework-free and test them independently. Run shared behavioral contract tests against real adapters where available; mocks alone do not validate integration.

## Integrating the existing model

### Available local model assets

The owner's trained model has been copied to `models/xtts_si_female/` in this workspace. The actual source folder was verified as `C:/D/Github Projects/PDF-Tool/voice-service/models/xtts_si_female/` (underscores belong in the directory name, not separate path components).

Local destination: `C:/D/Github Projects/Web-Page/models/xtts_si_female/`.

| Required file | Verified bytes |
| --- | ---: |
| `model.pth` | 5,607,762,519 |
| `vocab.json` | 376,645 |
| `config.json` | 4,526 |
| `sinhala_text.py` | 10,652 |
| `reference.wav` | 271,916 |

Only these five files belong in this local model bundle. Do not copy the source `archive/` or `__pycache__/`. The owner identifies `archive/` as an accidentally extracted duplicate checkpoint; leave the original source and archive untouched. Load `model.pth` as a checkpoint, not as an archive to unpack.

The owner confirms that `sinhala_text.py` / `to_ascii()` is the required text frontend, `reference.wav` is the separately supplied speaker-conditioning clip, and `vocab.json` must match the checkpoint. Keep all five assets together; do not replace the tokenizer or omit the reference audio. Runtime inference and dependency compatibility still need verification.

`/models/` is ignored by Git. Never force-add these assets, embed them in application images by accident, or upload them to GitHub. Configure the model directory through the application environment when implementing serving, mount it explicitly into the inference container, and provide a separate authorized artifact-delivery process for teammates and deployment. This local folder does not exist automatically on their machines.

Before connecting real inference, establish:

- Checkpoint location and exact artifact version/checksum.
- Existing working inference script and required tokenizer/configuration.
- Python, PyTorch, CUDA, and package requirements.
- Input text representation and current preprocessing.
- Required speaker reference or conditioning assets, if any.
- Output sample rate, format, text-length limits, hardware needs, and inference time.
- Model and dependency licenses relevant to the intended deployment.

Do not invent these details or substitute a different model without agreement. Independent application scaffolding can proceed with an explicitly labelled development adapter; never present mock audio as real model output.

Implementation requirements:

- Load the model once per worker process, not once per request.
- Preserve the known working preprocessing and inference settings initially.
- Bound concurrency and queue work to avoid GPU memory exhaustion.
- Support timeouts, cancellation, bounded retries, and actionable errors.
- Distinguish process liveness from model readiness.
- Record actual model version and synthesis settings for every generated segment.
- Keep model files and speaker recordings outside Git; use configuration to locate them.
- Never silently fall back to another language or voice.

Use an internal adapter equivalent to `synthesize(text, voice_id, settings) -> audio + metadata`. The public API should create asynchronous jobs rather than hold connections open for whole books.

### Model-specific checks from the reference project

The owner confirms the bundled `sinhala_text.py` / `to_ascii()` frontend and `reference.wav` conditioning asset. The seed documentation additionally reports an `en` language token; verify that token and all runtime settings against the actual config and working script before inference.

- Inspect the working script before passing raw Sinhala or choosing a language token. Never infer the token from the final entry of a language list or assume that the UI language is the inference token.
- If the model requires its bundled romanizer, preserve and version that exact implementation. Fail clearly when a required preprocessing asset is missing.
- Check whether preprocessing drops digits. Test years, prices, decimals, page references, and mixed-language input through the complete text-to-audio path. Any required number expansion happens before a lossy romanizer and only in spoken text.
- Preserve joiners and orthography in source/display text. Apply model-required transformations only in the speech adapter; do not globally strip characters based on reference notes.
- Cache speaker conditioning when supported by the working implementation, and verify permission to use the supplied speaker assets before public release.
- Measure dependency and audio-loader compatibility in the actual runtime; do not copy package pins or sample-rate assumptions from another project without testing.

If the checkpoint contains optimizer/training state, consider creating a separate inference-only artifact after confirming loader compatibility. Preserve the original checkpoint. Precision conversion is optional and must pass audio and performance evaluation; it is not required for integration and is not automatically equivalent in quality.

## Document pipeline

1. Validate file type, size, page count, and ownership. Process untrusted PDFs in constrained workers.
2. Classify pages independently; a PDF may contain both images and usable text.
3. Extract embedded text and detect garbled output or legacy Sinhala font encodings.
4. Run Sinhala OCR on image-based or unusable pages. Benchmark a baseline such as Tesseract on representative pages.
5. Recover reading order, headings, paragraphs, and repeated headers/footers.
   Structure may be inferred by a model under the verification rule above;
   captions, contents rows, and headings are separate blocks, never spliced
   into the sentence they sit beside.
6. Preserve original extraction, corrected display text, and separate spoken text.
7. Retain page index, printed page label when available, bounding boxes, and extraction provenance.
8. Flag uncertain extraction accessibly. OCR scores are not calibrated correctness probabilities.
9. Split speech into sentence-aware chunks within the model's measured limits.
10. Generate the first requested section before processing the remainder.
11. Build separate section-aware passages for retrieval.

Evaluate Unicode normalization, numbers, dates, abbreviations, punctuation, and Sinhala-English mixing without silently changing meaning. Do not use speech-expanded text as the only source for display or retrieval.

Text corrections create a new document version and invalidate affected audio and retrieval entries. Jobs must be idempotent and resumable.

### Legacy fonts and extraction validation

This repository includes `data/legacy_fonts/fm_abhaya.tsv` and `fm_abhaya_cases.tsv`, with six supplied conversion examples copied unchanged from the user-supplied reference. Their README records provenance and copy-verification hashes, and the upstream MIT license is included. Resolve these assets relative to the repository/package; do not depend on the seed project's absolute local path. The converter is implemented in `services/worker/src/sinhala_documents/legacy_fm_abhaya.py` and tested against every supplied case.

- Inspect per-span font metadata and normalize subset prefixes when identifying a legacy font. Pages may mix Unicode headings and legacy body text; decode at span/line level rather than applying one mapping to the entire page.
- Reuse the documented mapping rather than inventing one. Preserve its included license and attribution, and verify provenance for any future additions or replacements.
- The supplied table specifies two ordered passes, `[rules]` then `[letters]`, each using longest-match-first application. Preserve its documented semantics and test all supplied examples character-for-character.
- Do not apply an FM-Abhaya table to another font family without validated compatibility. Route unsupported or failed conversions to OCR/review and announce the limitation.
- A high proportion of Sinhala codepoints does not prove correct conversion. Evaluate unmapped letters and invalid combining-mark sequences, including English and mixed-language negative examples.
- Orthography checks can detect malformed text but cannot establish transcription accuracy or rule out plausible OCR hallucinations. Calibrate thresholds against ground truth and human review; do not adopt the reference's numerical thresholds as proven defaults.
- Keep extraction method (`native`, `legacy`, `ocr`) separate from quality state (`accepted`, `needs_review`, `undecodable`). Block known-undecodable spans from narration and RAG while allowing access to valid sections.
- Retain geometry while assembling text so sentence-to-page mappings are traceable. Handle layout ambiguity explicitly; do not assume flattened extraction preserves column order.
- Remove repeated headers/footers using both recurrence and page position, with tests that preserve repeated story refrains and legitimate prose.
- Test segmentation with Sinhala abbreviations, decimals, initials, filenames, and missing punctuation. Bound chunks using actual model limits rather than copying a fixed character cap.

If an external vision OCR provider is introduced, make it configurable, disclose external document processing, apply page/cost limits, and benchmark it before choosing a default. Cache by content plus extraction engine/model/prompt/settings version; preserve page IDs when asynchronous results arrive out of order.

## Playback and caching

- Map audio segments to stable sentence IDs for sentence highlighting.
- Do not promise word-level timestamps without a validated alignment method.
- Prefetch upcoming segments while allowing immediate pause and navigation.
- Persist document version, segment ID, and playback offset for resume.
- Include text hash, document version, model version, normalizer version, voice, and generation settings in cache identity.
- Keep private audio access-controlled even when generated content is cached.
- Test browser storage limits and offline playback on target mobile devices.
- Deduplicate in-flight synthesis requests so prefetch and playback cannot generate the same segment twice.
- Expose cold-start/queue progress and offer retry or cached playback during an inference outage. A separately evaluated fallback voice is optional, requires an explicit product decision, and must be announced accessibly if used; never silently substitute voices or move overloaded inference to CPU.
- Validate speed controls for pitch preservation, intelligibility, and the actual engine's supported range.

## RAG implementation

- Retrieve only from documents the authenticated user is authorized to access; enforce this before search results reach the LLM.
- Begin with section-aware passages of approximately 300–600 model tokens and tune using evaluation.
- Preserve document version, section, and exact page references with each passage.
- Compare lexical, dense, and hybrid retrieval. Multilingual model claims do not establish Sinhala quality.
- Add reranking only when measured improvements justify latency and complexity.
- Generate Sinhala answers supported by retrieved evidence.
- Return navigable citations and allow users to hear or open the source passage.
- Abstain when the available evidence cannot answer the question. Do not fabricate citations.
- Treat document contents as untrusted evidence, never as instructions to the assistant or application.
- Keep prompts, embedding configuration, retrieval settings, and index versions reproducible.
- Avoid cross-document answers unless the user explicitly selects an authorized collection.

Typed questions are sufficient for the initial release. Send generated answer text through the same TTS service.

## Accessibility requirements

Target WCAG 2.2 AA and validate with people who use assistive technology.

- Semantic controls, meaningful accessible names, logical focus order, visible focus, and full keyboard operation.
- Accessible processing progress, errors, and recovery actions.
- Page, chapter, and sentence navigation without relying on visual highlighting.
- No automatic narration on page load; avoid competing with screen-reader speech.
- Readable Sinhala typography, adequate contrast, and touch-friendly controls.
- Test core tasks with NVDA and Android TalkBack.
- Treat inability to upload, play, pause, navigate, or resume with assistive technology as a release blocker.
- Make Sinhala the primary UI language and have controls, errors, and status messages reviewed by a native speaker. Set appropriate language metadata and test how target assistive technologies announce the interface; Sinhala audio content alone does not make navigation accessible.
- Use polite live regions for routine progress and reserve assertive alerts for urgent errors. Avoid announcing every prefetch or intermediate update.

## Accounts, roles, and authorization

- **Roles** are student, teacher, and admin. Registration always creates a
  student. A teacher is made by an admin or by a single-use invitation. Nobody
  can declare their own role.
- **Admins have no content access.** Administration happens on the command line.
- **Reading** is allowed to a document's owner, or to an active member of a
  class the book is published to, at the version pinned when it was published.
  **Writing** (rename, delete, publish, pre-render, authoring quizzes) is
  owner-only.
- Enforce this in the store, never only in a route. Anything a reader may not
  see is absent (404), never forbidden (403). The cross-access matrix across
  actors, resources, and routes is a release gate.
- A teacher never sees a student's private books, bookmarks, notes, or
  questions. A teacher sees class progress only from students who chose to
  share it. That choice is off by default and can be withdrawn.
- **Sessions** use an httpOnly, `SameSite=Lax` cookie through a same-origin
  route handler, with CSRF and Fetch-Metadata checks. Rate-limit sign-in,
  registration, recovery, and costly requests. Do not use CAPTCHAs; they are
  inaccessible. Recovery works without email, through a one-time recovery code
  or a reset issued by the student's own teacher.
- Publishing a book requires the teacher to attest the permission that clears
  it for their class, and records who attested it and on what basis. The system
  cannot verify that permission itself, so sharing stays class-limited,
  audited, and withdrawable.

## Data and API design

Core entities: User, Document, DocumentVersion, Page, TextSegment, AudioSegment, ProcessingJob, ReadingProgress, Bookmark, QuestionAnswer, Feedback, ModelRelease, Class, ClassMember, PublishedBook, Quiz, Question, QuizAttempt, and ReviewCard.

Use explicit job states such as queued, running, succeeded, failed, and cancelled. Store stage-specific failure details without leaking private content.

Suggested API capabilities:

- Upload/list/delete documents and inspect processing status.
- Fetch document structure and text segments.
- Request audio generation and retrieve authorized audio manifests.
- Save reading position and bookmarks.
- Ask a document question and return an answer plus citations.
- Submit extraction or pronunciation feedback.
- Create classes, join them, and publish reviewed books to them.
- Generate, review, take, and resume practice quizzes; record spaced review.
- Report reading coverage and progress.
- Expose internal health/readiness and operational metrics.

Validate contracts on the server. Use expiring authorized object access and enforce ownership for every operation.

## MLOps scope: serving and evaluation

There is no training pipeline in this project scope.

- Version checkpoint artifacts, configuration, tokenizer, environment, and preprocessing.
- Record Git commit and runtime configuration for reproducible releases.
- Maintain a fixed Sinhala inference regression set.
- Measure first-audio latency, real-time factor, queue wait, errors, GPU memory, and cost per generated audio hour.
- Detect empty, failed, or suspiciously short/long outputs and route failures for review.
- Release through staging, verify with the fixed suite, and retain a tested rollback path.
- Collect pronunciation and OCR feedback for review, not automatic retraining.
- Monitor changes in document length, scan quality, vocabulary, and code mixing.

MLflow is optional for the initial fixed checkpoint. Use it when tracking experiments across serving configurations or multiple releases adds value; otherwise immutable artifacts and release manifests suffice.

Deployment must resolve a release label to an immutable artifact revision/checksum and record what was actually loaded. Rollback restores the previous artifact and compatible serving configuration, reloads/redeploys the worker, and verifies readiness plus real synthesis; changing a registry tag alone does not change a running process.

Audio regression checks must inspect decoded samples for finite values, non-silence, clipping, sample rate, and plausible duration. A correctly formed WAV can still contain silence. For stochastic generation, do not require byte-identical outputs; use repeated measurements where needed and human listening for intelligibility. Do not use English-ASR transcription of romanized Sinhala as a release gate unless it has first been validated against native-listener judgments.

## Research and evaluation

Working research title: **Design and Evaluation of an Accessible Sinhala Document Reader with Integrated TTS and Retrieval-Augmented Question Answering**.

The contribution is integration and measured system improvement, not new TTS training.

Evaluate:

| Question | Comparison | Measures |
| --- | --- | --- |
| Does segmentation improve narration? | Fixed-size vs sentence-aware chunks | Listening preference, omissions/repetitions, latency |
| How do extraction errors affect listening? | Clean vs OCR vs reviewed text | Character error rate, pronunciation, comprehension |
| Which retrieval works for Sinhala? | Lexical vs dense vs hybrid | Recall@5, answer correctness, citation support, abstention |
| Does caching improve operation? | Cached vs uncached sessions | Playback delay, GPU time, unit cost |
| Can users read independently? | Counterbalanced representative tasks | Completion, time, assistance required |
| Does the verifier make generated questions safe? | Full generation vs verification bypassed vs no model check, rated blind by teachers | Grounded rate, verifier false accepts (the safety measure) and false rejects, rater agreement, cost per accepted question |
| Model-drafted vs fill-in-the-blank questions | Teacher ratings, review data, and student attempts | Approval rate, time to approve, item difficulty and discrimination |
| Can students complete the learning loop alone? | Counterbalanced listen, ask, practise, and revise tasks | Completion, time, assistance required, errors; no learning-gain claim |
| Does pre-rendering class books fix latency and cost? | On-demand vs pre-rendered audio | First-audio p50/p95, CPU hours vs GPU seconds, storage per audio hour |

Start with 300–500 held-out sentences, 50–100 manually transcribed pages, and 150–250 questions with supporting passages and unanswerable examples. These are planning quantities, not collected assets.

Split document evaluation by book/source to prevent leakage. Use blinded listening comparisons, human Sinhala review, and confidence intervals where appropriate. ASR-derived scores are supplementary because recognition errors can confound TTS evaluation.

Run a formative study with blind/low-vision readers and students. Obtain informed consent and applicable institutional research approval. Determine final sample sizes from pilot results and intended claims; do not invent outcomes.

## Provisional release targets

These are targets to refine after baseline measurements, not performance claims:

- No critical accessibility blockers in core tasks.
- At least 90% core-task completion in the pilot.
- No material speech intelligibility regression against the existing inference baseline.
- Retrieval Recall@5 of at least 85% on held-out questions.
- At least 90% citation-supported answers and 90% correct abstention on their respective evaluation sets.
- Cached playback starts within 2 seconds at p95 on a specified network/device.
- First short synthesized segment within 5 seconds at p95 on declared hardware and load, excluding PDF/OCR processing.
- Safe retry behavior, tested model rollback, and passing cross-user access checks.
- The cross-access matrix passes, including class members, removed members, and admins.
- No question reaches a class without passing the verifier and a teacher's approval.

Measure sustained synthesis speed as well as first-segment latency to detect playback stalls.

## Privacy and deployment constraints

- Keep uploads private by default and do not use them for training without separate explicit opt-in.
- Do not log full private passages or prompts by default.
- Deletion must remove derived text, embeddings, audio, and caches; document backup retention separately.
- Store secrets in environment/secret storage, never source code or browser bundles.
- Apply upload limits, quotas, request rate limits, and retention controls.
- Use permission-cleared content for shared libraries and research assets.
- Students may be minors. Obtain legal review and guardian consent before any pilot, and collect only what a feature needs. Do not claim compliance with data-protection law without that review.
- Clear offline audio caches on sign-out and account deletion; phones are shared.
- Audit the supplied checkpoint's provenance. XTTS-v2 weights under CPML have non-commercial restrictions; fine-tuning does not automatically remove them. Resolve applicability before a commercial release.

## Implementation order

The reader itself (inference, the adapter, PDF to audio, bookmarks, caching,
OCR, and cited answers) is built. What remains follows the phases in
[`docs/product-plan.md`](docs/product-plan.md), each with an exit gate that
includes an NVDA or TalkBack pass on the new core task:

0. **Foundation.** Fix the defects that sit under the new features: the voice image, segment roles lost on reload, role-aware text reaching the voice, structure in the document version, the audio cache for a second reader, jobs that outlive their process, page titles, and contrast checking.
1. **Portal and real accounts.**
2. **Class library** with reviewed, attested, pre-rendered books.
3. **Practise:** fill-in-the-blank questions and the quiz screen first, then model-drafted questions with teacher review.
4. **Track:** coverage, progress, and spaced review.
5. **Reader additions:** pasted text, in-book search, problem reports, and offline chapter download.
6. **Evaluation and the user study.**
7. **Release:** staging, observability, load and failure tests, rehearsed rollback.

[`docs/upgrade-roadmap-50-commits.md`](docs/upgrade-roadmap-50-commits.md) runs alongside as the quality track.

## Development and completion rules

- Deliver small end-to-end increments and preserve working behavior.
- Inspect existing conventions before selecting dependencies or reorganizing code.
- Ask for missing model assets/configuration when required; continue independent work where possible.
- Keep mocks explicitly labelled and never claim unexecuted checks passed.
- Test critical behavior: permissions, deletion, correction invalidation, job retries, source citations, playback resume, and accessibility.
- Use real model smoke tests when assets and hardware are available. Record any unavailable verification clearly.
- Document actual setup, environment variables, migrations, commands, and deployment steps as they are implemented. Do not invent runnable commands before tooling exists.
- Keep a model/inference manifest, architecture notes, evaluation protocol, benchmark results, and operator runbook.
- Product UI should explain user-relevant state and limitations without exposing infrastructure jargon.

## Git commits, identity, and automatic pushing

The project owner explicitly requests that Claude Code **commit and push automatically after every small, completed implementation increment**. This is standing authorization for ordinary commits and pushes to the current task branch; do not repeatedly ask for permission. It does not authorize bypassing branch protections, force-pushing shared history, merging without review, or publishing secrets/private assets.

A small increment is one coherent, reviewable change, such as an endpoint, reader control, adapter, bug fix, or configuration improvement. Do not wait until the entire feature or task is finished, and do not create commits for every individual file edit.

For each increment:

1. Inspect the branch, remote, working tree, and existing changes. Use a short-lived task branch, never implement directly on protected `main`.
2. Complete the change and run relevant available checks. Fix failures caused by the change before committing; disclose unavailable checks without claiming success.
3. Review the diff for unrelated edits, credentials, private documents, model weights, generated audio, and other large artifacts. Stage only files belonging to the increment.
4. Commit with a concise descriptive message, preferably `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, or `ci:`.
5. Push the commit to the verified task branch, setting its upstream on the first push. Verify success and report the branch and commit hash with a concise outcome.
6. If authentication, connectivity, permissions, or a non-fast-forward rejection blocks pushing, preserve the local commit, explain the blocker, and resolve it without force-pushing or discarding teammates' work. Never report an unpushed commit as pushed.

### Human authorship only

- For work Claude Code performs on behalf of the project owner, use the owner's confirmed Git name and email for author and committer. Check the effective Git identity first; do not invent an identity or copy a teammate's from repository history.
- If the correct identity is unknown or mismatched, obtain the owner's name/email once before committing. Prefer repository-local Git configuration; never change global Git identity for this project.
- Do not add Claude, Anthropic, an AI bot, `Co-authored-by: Claude`, or generated-by attribution to commits or pull-request descriptions. Honor this through Claude Code's supported attribution configuration when available, verifying the installed version's setting format before editing it.
- Inspect the actual commit metadata/message to confirm the human identity and absence of automatically inserted AI trailers. GitHub attribution also depends on the email being associated with the owner's account; use a confirmed account email or GitHub noreply address.
- These instructions apply to the owner's assisted changes. The other two collaborators retain authorship of their own commits. Never rewrite their authorship, impersonate them, or remove legitimate human attribution.
- Configure changes prospectively. Do not rewrite already-pushed history just to change attribution without a separate explicit request.

## Three-person GitHub collaboration

This project is developed by the owner and two other members. Repository setup is an implementation task, not something already completed by this document.

### Initial setup

- Inspect the existing Git remote and GitHub repository before creating anything. Preserve the intended repository and its existing history.
- Obtain missing repository owner/name, visibility preference, and the two collaborators' GitHub usernames before dependent setup. Do not guess identities or publish a private repository.
- Keep the owner as administrator and grant collaborators the least privilege needed to push task branches and review PRs, normally write access.
- Use protected `main` as the integration/release branch and short-lived branches such as `feat/<issue>-<topic>`, `fix/<issue>-<topic>`, or `chore/<topic>`. Follow an established branch convention if one already exists.
- Track bounded work in GitHub issues with acceptance criteria and a named owner. Divide ownership by area while allowing cross-review; keep coordination in `CONTRIBUTING.md` and issues.
- Add `.github/PULL_REQUEST_TEMPLATE.md`, issue templates, `CONTRIBUTING.md`, and `.github/CODEOWNERS` using confirmed usernames. Cover frontend/accessibility, backend/document processing, and inference/operations with a primary and backup reviewer where practical.
- Create or update a draft PR after the first useful increment and keep pushing small commits to that PR. Mark it ready only when its acceptance criteria and relevant checks pass. The owner's standing workflow authorization includes these task PRs, but not automatic merging.

### Main-branch rules

Configure available GitHub rulesets/branch protection to require:

- Pull requests for changes to `main`, with at least one approval from another team member.
- Required CI checks and resolved review conversations before merging.
- Dismissal of stale approvals when new commits change reviewed code.
- An up-to-date branch before merging, or a supported merge queue if later justified.
- No force pushes or branch deletion; avoid routine administrator bypass.
- Review of workflow, deployment, and sensitive infrastructure changes by the responsible human owner.

Use a merge strategy that preserves the intended human attribution; verify squash author/message before a human merges. Automatically pushing task commits does not mean automatically merging or deploying them to production.

Protection features depend on the repository's visibility, GitHub plan, and permissions. Verify availability during setup and document any unenforced rule explicitly. A `CODEOWNERS` or workflow file alone does not enable server-side branch protection.

## CI/CD implementation requirements

Build workflows alongside the first runnable services, using actual project commands. Do not add required status names for checks that do not exist or let a skipped placeholder stand in for a passing test.

### Pull requests and task-branch pushes

- Run formatting/linting, type checks, focused unit/contract tests, and frontend production builds for implemented components.
- Add PostgreSQL/Redis integration tests for authorization, job idempotency, and cache invalidation as those components arrive.
- Run an accessibility smoke test on core reader flows; retain manual screen-reader testing as a separate release requirement.
- Validate Docker builds and scan relevant dependency/secret changes using available tooling. Cache dependencies and cancel superseded branch runs.
- Keep an always-reported aggregate required check so path-filtered jobs cannot leave PRs permanently pending or bypass meaningful checks. Configure its dependencies to fail on errors or cancellations.
- Use minimal workflow token permissions and pin external actions to reviewed immutable revisions. Never expose deployment/model credentials to untrusted PR code or run it on a privileged self-hosted GPU runner.
- Fast PR tests may use labelled adapters. Real-model smoke tests run on a trusted, access-controlled GPU environment before inference releases; distinguish these results clearly.

### Staging and production

- After a reviewed merge to `main`, build immutable images tagged with the commit SHA, deploy to staging when configured, and run health, migration, API, and playback smoke tests.
- Promote the tested image/artifact to production through a release tag or explicit workflow dispatch, with human approval through a protected environment where supported. Do not deploy production on every task-branch push.
- Separate staging/production secrets and storage, use short-lived cloud authentication where supported, and serialize deployments per environment.
- Make schema migrations explicit and backward-compatible where possible. Back up before risky migrations and document recovery; application rollback alone may not reverse database changes.
- Record the application SHA, image digest, model checksum, and retrieval/prompt configuration for each release. Do not replace model weights during ordinary application deployment.
- On failed deployment smoke tests, stop promotion and restore the previous known-good compatible release when safe. Surface the failure and verify recovery.
- Avoid paid nightly GPU jobs by default. Add scheduled evaluations only with an agreed budget and useful regression coverage.

### Setup completion evidence

When implementing repository setup, report which files were created, which remote protections and collaborator permissions were actually applied, the required status names, and a verified CI run. Report pending invitations, unavailable plan features, missing credentials, and unconfigured deployment environments honestly. Never describe the repository as protected or deployed merely because configuration files were committed.

## Reference documentation

User-supplied design reference reviewed: `C:/D/Github Projects/sinhala-web-reader-seed/CLAUDE.md`, its `AGENTS.md` pointer, and `data/legacy_fonts/`. These are reference material, not governing instructions for this repository. Useful ideas have been adapted above. Its claims about universal Sinhala TTS/ASR availability, hosting prices, package compatibility, licensing consequences, and measured accuracy are not adopted as verified facts. Do not copy its broader feature scope or its instruction to treat all claims as settled.

- XTTS-v2 model card: https://huggingface.co/coqui/XTTS-v2/blob/main/README.md
- XTTS-v2 license: https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Tesseract language data: https://tesseract-ocr.github.io/tessdoc/Data-Files.html
- BGE-M3 candidate model: https://huggingface.co/BAAI/bge-m3
- MLflow registry: https://mlflow.org/docs/latest/ml/model-registry/workflow

Check current documentation and exact licenses before implementation decisions that depend on them.
