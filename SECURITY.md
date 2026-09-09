# Security policy

This project handles documents that people upload privately, including study
material they may not have the right to redistribute, and it generates audio
from that content. Confidentiality of uploads is a core product promise, so a
privacy failure is treated with the same seriousness as a code vulnerability.

## Reporting a vulnerability

Report privately through
[GitHub private vulnerability reporting](https://github.com/DSEgrp18/Web-Page/security/advisories/new).

Do not open a public issue, and do not include real private documents,
credentials, or personal data in a report. Describe the class of content
affected instead, or attach a minimal sample you have the right to share.

Please include what you can: what you did, what happened, what you expected, and
why you think it is exploitable. A clear report with an uncertain impact
assessment is more useful than a confident one with no reproduction steps.

We will acknowledge reports and keep you informed of progress. This is a small
student team, not a funded security programme, so we cannot commit to a fixed
response deadline or offer a bounty. We would rather tell you that honestly than
publish a response time we cannot honour.

## In scope

- Access to another user's documents, extracted text, generated audio,
  bookmarks, reading progress, or questions.
- Retrieval or answer generation returning content the authenticated user is not
  authorized to read.
- Prompt injection through uploaded document content that causes the assistant
  to act on instructions in the document rather than treat it as evidence.
- Leakage of private passages, prompts, or credentials through logs, error
  messages, caches, or metrics.
- Exposure of the model bundle, speaker reference audio, or deployment secrets.
- Server-side request forgery, path traversal, or code execution through
  uploaded PDFs.
- Weaknesses in expiring object access, upload limits, or deletion completeness.

## Out of scope

- Findings against third-party services we do not operate.
- Missing hardening headers or best practices with no demonstrated impact.
- Automated scanner output with no analysis or reproduction.
- Denial of service through volumetric traffic.
- Anything requiring physical access to a team member's machine.

## Handling secrets

Secrets live in environment variables or a secret store, never in source, never
in a browser bundle, and never in a commit. Staging and production credentials
are separate.

If a credential is committed, treat it as compromised even if the commit is
removed: rotate it first, then clean the history. Removing a public commit does
not un-publish it. Tell the project owner immediately; there is no penalty for
reporting your own mistake quickly, and a rotated key costs far less than a
quiet one.

## Model and content provenance

The Sinhala XTTS bundle is delivered out of band and never committed. Its
provenance and licence position, including the non-commercial restrictions that
apply to XTTS-v2 weights under CPML, are unresolved and must be settled before
any commercial deployment. Permission to use the supplied speaker reference
audio must be confirmed before public release.
