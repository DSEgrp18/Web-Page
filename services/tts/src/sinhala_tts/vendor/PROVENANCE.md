# Vendored text front end

## What this is

`sinhala_text.py` is the text front end the Sinhala XTTS checkpoint was
fine-tuned with. It is vendored here, unchanged, because **inference must use
the same front end as training**. A front end that differs from training does
not degrade quality gracefully; it produces fluent-sounding nonsense.

The reason is specific and worth understanding before touching anything here.
XTTS-v2's tokenizer is a whitespace-pretokenised BPE with an `[UNK]` fallback,
and the Sinhala block (U+0D80–U+0DFF) is absent from its vocabulary entirely.
Because the pre-tokeniser splits on whitespace and the BPE falls back to `[UNK]`
for the *whole word* when any character is unknown, one Sinhala codepoint
destroys the entire word. The fine-tune works by romanising Sinhala into ASCII
the base model already knows and training under the English language token, so
the task becomes "learn an accent" rather than "learn a script".

`to_ascii()` is that romanisation. Skipping it does not lower quality — it
destroys the output.

## Source and verification

Copied from the model bundle at
`models/xtts_si_female/sinhala_text.py`, which is delivered out of band and is
not in Git. Originally from the owner's training project
(`PDF-Tool/voice-service/models/xtts_si_female/`).

| Property | Value |
| --- | --- |
| Source size | 10,652 bytes (matches the size recorded in `CLAUDE.md`) |
| Source SHA-256 (as delivered, CRLF) | `f8f41fa44de13bb93a6f1de47a6b1d1aabc3162feadd6171c170ea8520919c92` |
| Vendored SHA-256 (line endings normalised to LF) | `c36d9864696b87ea46743cd6c860aeb14a44d9c6e9d979062f97554b9ecdd0dd` |

The delivered file uses CRLF line endings. This repository normalises stored
text to LF (see `.gitattributes`), so the vendored copy is **not** byte-identical
to the delivered file: it differs in line endings and nothing else. The
LF-normalised hash above is therefore the one to verify against, and
`tests/test_vendor_integrity.py` checks it on every CI run. It is computed by
reading the file as bytes and replacing `\r\n` with `\n`, so it is stable on
every platform regardless of checkout settings.

## Rules for this file

- **Do not edit it.** Not to fix style, not to satisfy a linter, not to correct
  the inaccuracy noted below. Its behaviour defines what the model heard during
  training, so any change silently alters pronunciation.
- It is excluded from linting and formatting for the same reason.
- If the model is ever retrained with a different front end, replace this file
  and update both hashes and the manifest in the same commit.
- Known limitations are handled by *wrapping* it, never by modifying it. See
  `docs/model-inference-manifest.md`.

## Known inaccuracy in its own docstring

The module docstring claims the output charset is
`" !'(),-.:;=?abcdefghijklmnoprstuvy"`, which includes `(`, `)`, and `=`. The
code does not produce those: `_KEEP` in `_normalise()` is
`" !',-.:;?abcdefghijklmnopqrstuvwxyz"`, so parentheses and `=` are stripped.
The measured behaviour, not the docstring, is authoritative. This is recorded
here rather than corrected in the file, because the file must stay unchanged.

## Licence

Written by the project owner as part of this project's own training work. It
carries the same MIT licence as the rest of this repository. It is vendored
rather than imported because the model bundle is not on any teammate's machine
and is not installable.
