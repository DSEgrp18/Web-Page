# services/tts

The Sinhala XTTS text front end, and eventually the inference adapter.

Right now this package contains **only the text path**. Model loading and
synthesis are not implemented yet. That order is deliberate: the text front end
is where this model is most easily broken, it is pure standard library, and it
can be tested exhaustively without a GPU or the 5.6 GB checkpoint — so it is the
part worth getting right and locking down first.

See [`docs/model-inference-manifest.md`](../../docs/model-inference-manifest.md)
for the verified inference procedure, settings, limits, and dependencies.

## Why the text front end matters this much

XTTS-v2's tokenizer is a whitespace-pretokenised BPE with an `[UNK]` fallback,
and the Sinhala block is absent from its vocabulary. One Sinhala codepoint turns
the **whole word** into `[UNK]`. The fine-tune works by romanising Sinhala into
ASCII the base model already knows and training under the English language
token.

So `to_ascii()` is not a nicety. Skipping it does not produce worse audio; it
produces confident-sounding babble. The vendored front end must match training
exactly, which is why CI verifies its hash and lint never touches it.

## Running the checks

From this directory, with Python 3.12 or newer:

```bash
python -m pip install "pytest>=8" "ruff>=0.15"
python -m pytest
ruff check .
ruff format --check .
```

No install step is needed: `pyproject.toml` puts `src` on the test path
directly. On Windows, set `PYTHONIOENCODING=utf-8` first or the console cannot
print Sinhala test output.

## Layout

```text
src/sinhala_tts/vendor/    The training front end, vendored unchanged. Do not edit.
tests/                     Characterisation and integrity tests.
```

## What the tests establish

`test_vendor_integrity.py` verifies the front end has not been altered, by
hashing it with line endings normalised so the check holds on any platform.

`test_text_frontend_characterisation.py` records what the front end **actually
does**, measured rather than assumed. It includes three behaviours that are
defects for a document reader, each marked `DEFECT`:

1. **Digits are silently deleted.** `"පිටුව 42 බලන්න"` → `"pituva balanna"`.
   Years, page numbers, prices, and decimals all vanish silently.
2. **Newlines and tabs are deleted, not collapsed**, gluing words together.
   PDF text is full of line breaks, so this corrupts roughly a word per line.
3. **English-only text is romanised as if Sinhala**: `"computer"` →
   `"chomputher"`. English inside a Sinhala sentence is unaffected, which is
   what makes it easy to miss.

These tests assert the defects on purpose. They are not approval of the
behaviour — they make it visible and make any change to it fail loudly.

## The rule for fixing those defects

**Wrap the front end; never edit it.** Its behaviour is what the model heard
during training, so changing it silently alters pronunciation and invalidates
the fine-tune. Number expansion and whitespace normalisation belong in a
normaliser that runs *before* `to_ascii()`, because the front end is lossy and
nothing can be recovered afterwards.

That normaliser is the next increment. When it lands, the `DEFECT` tests stay as
they are — asserting the raw front end is unchanged — and new tests assert the
corrected end-to-end pipeline.
