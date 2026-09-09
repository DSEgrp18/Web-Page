## What this changes

<!-- One paragraph. What behaviour is different after this merges? -->

Closes #

## Why

<!-- The problem being solved. Link the issue's acceptance criteria if they are not repeated below. -->

## How it was verified

<!--
List the checks you actually ran and their result. Leave unrun checks unticked
and say so under "Not verified" rather than ticking them optimistically.
CLAUDE.md: never claim an unexecuted check passed.
-->

- [ ] Automated checks in CI pass
- [ ] Unit / contract tests added or updated for the changed behaviour
- [ ] Verified manually (describe below)

Not verified, and why:

## Accessibility

<!--
Required for any change that touches the reader UI, its markup, focus order,
status messages, or audio playback. Write "Not applicable" with a reason for
backend-only changes.

Inability to upload, play, pause, navigate, or resume with assistive technology
is a release blocker, not a follow-up.
-->

- [ ] Fully operable by keyboard, with a visible focus indicator
- [ ] Controls have meaningful accessible names, and status uses an appropriate live region politeness
- [ ] No narration starts automatically on load
- [ ] Screen reader checked (state which: NVDA / TalkBack / other, and what was tested)

## Read mode and Study mode

<!-- Delete if this change touches neither. -->

- [ ] Read mode still narrates extracted and reviewed document text without LLM rewriting
- [ ] Any AI-generated content is clearly labelled as such
- [ ] Citations point at real, retrievable passages with correct page references

## Model, data, and privacy

- [ ] No model weights, speaker audio, private documents, generated audio, or secrets are added
- [ ] No full private passages or prompts are written to logs
- [ ] If synthesis behaviour changed, the recorded model version and settings are still accurate
- [ ] If text or extraction changed, affected audio and retrieval entries are invalidated

## Risk and rollback

<!-- What could break, how would you notice, and how do you undo it? Note any migration that is not backward compatible. -->

## Reviewer notes

<!-- Where to start reading, decisions you want challenged, known gaps. -->
