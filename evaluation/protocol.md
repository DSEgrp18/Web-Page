# Evaluation protocol

**Status:** draft, for supervisor review and institutional ethics approval. Nothing that involves
a person runs before that approval, and nothing that involves a student under 18 runs without
guardian consent and the student's own assent.

**Contribution:** integration and *measured* system improvement. There is no new model training
and **no claim about learning gains**.

Sample sizes below are planning figures. The final numbers come from the pilot and from the
claims we decide to make; we will not invent results or report a number we did not measure.

## Common rules

- **Split by book.** No book used during development, or to tune a threshold, is used to evaluate.
- **Blinding.** Raters and listeners never see the condition. Keys stay with the researcher.
- **Intervals.** Rates carry 95% percentile bootstrap intervals (2,000 resamples, seeded).
  Latencies are reported as p50 and p95.
- **Aggregates only leave `data/`.** See `README.md`.
- **Declared conditions.** Every latency or cost result names the device, network and server it
  was measured on.

## RQ1: Does the verifier make generated questions safe?

**Design.** The same held-out chapters, under three conditions:

| Condition | Verifier | Blind check |
| --- | --- | --- |
| `full` (the product) | on | on |
| `no_verifier` | off; its verdict is recorded after the fact | on |
| `no_blind_check` | on | off |

**Raters.** At least two Sinhala subject teachers rate every question blind to its condition,
using `rubrics/question-rubric.md`: *grounded*, *ungrounded* or *unclear*. The majority label is
used, and ties and *unclear* are excluded, reporting how many were.

**Measures.**
- Grounded rate per condition, with intervals.
- Rater agreement: Krippendorff's α, nominal.
- **Verifier false accepts**: questions it passed that the raters judged ungrounded. **This is the
  safety measure.**
- Verifier false rejects: questions it failed that the raters judged grounded. This is its cost.
- How often each rejection code fires, and how many rejections disappear when zero-width joiners
  are removed (whether Sinhala joiners cause the verifier to reject too much).
- Model calls, seconds and calls per accepted question, per condition.

**Planning size.** 3–5 held-out chapters, and about 150 rated questions across the conditions.

## RQ2: Model-drafted questions against fill-in-the-blank

**Data.** Teacher ratings from RQ1's `full` condition alongside cloze questions from the same
chapters, the product's own review data (questions removed before publishing, and time to
publish), and students' answers once quizzes are in class use.

**Measures.**
- How often teachers approve each kind, and how long approval takes.
- How hard each question is: the proportion answering correctly.
- How well it separates stronger students from weaker ones: the point-biserial correlation, when
  there are enough answers.
- Students' preference.

## RQ3: Can blind and low-vision students complete the learning loop on their own?

**Design.** A formative study, with the task order counterbalanced across participants. It is
run with each participant's own assistive technology (NVDA or TalkBack) and device, both of
which are recorded.

| Task | Done when |
| --- | --- |
| `find_and_hear_chapter` | The named chapter is playing |
| `ask_and_hear_source` | An answer is heard, then its cited source |
| `quiz_and_hear_missed_source` | A quiz is finished, and the source of a missed question is heard |
| `find_what_to_revise` | The participant says what is due, from `/progress` |
| `teacher_publish` (teachers) | A book is reviewed, attested and published to a class |

**Measures.**
- Completion.
- Time on completed tasks.
- Assists: any help from the facilitator.
- Errors.
- UMUX-Lite. Its Sinhala translation has not been validated, and results say so.
- Think-aloud notes, kept in `data/` and summarised as themes only.

**Stopping rule.** A task stops at 10 minutes, or when the participant asks. Distress ends the
session.

**Planning size.** 6–10 students, and 2–4 teachers.

## RQ4: Does pre-rendering fix latency and cost?

**Design.** On-demand and pre-rendered audio for the same sentences.
- **Device:** a declared low-cost Android phone.
- **Network:** a declared throttled connection.
- **Server:** declared hardware, whether CPU, GPU or Modal.

**Measures.**
- First audio at p50 and p95 (`rq4-latency`).
- CPU hours or GPU seconds to pre-render one book.
- Cost per audio hour.
- Megabytes per audio hour for WAV and for Opus (`rq4-sizes`).
- **A blind WAV-against-Opus listening comparison** (`rq4-pairs`, `rq4-listening`), with an
  exact sign test. Opus stays off in the product until this finds no audible cost.

## Existing measures (from `CLAUDE.md`)

- **Retrieval Recall@5** on held-out questions with gold pages (`retrieval`). The target is at
  least 85%.
- **Citation support and correct abstention**, each with a target of at least 90%, measured on
  the answerer's output, with 150–250 questions including unanswerable ones.
- **OCR character error rate** on 50–100 manually transcribed pages.
- **Segmentation**: fixed-size against sentence-aware chunks, by listening preference, omissions
  and latency.

## Threats to validity

- **Small samples.** RQ3 is formative; completion rates are described, not generalised.
- **The rubric decides "grounded".** Rater training and agreement are reported, not assumed.
- **Provider drift.** The model and prompt versions are recorded with every run; a provider
  update between conditions voids the comparison.
- **A novelty effect in RQ3.** We report first-session use only.
