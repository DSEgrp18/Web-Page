# Legacy Sinhala font mappings

These small reference assets support future FM-Abhaya-to-Unicode conversion. A converter is not implemented yet.

## Files

- `fm_abhaya.tsv`: mapping data with `[rules]` followed by `[letters]`. Apply each pass left-to-right, longest-key-first, as documented in its header.
- `fm_abhaya_cases.tsv`: six supplied legacy-input/expected-Unicode examples for exact conversion checks.
- `LICENSE`: upstream MIT license and copyright notice.

The TSV files were copied unchanged from the user-supplied `sinhala-web-reader-seed/data/legacy_fonts/` directory. Its documentation attributes the data to [akuruAI/Pandukabhaya](https://github.com/akuruAI/pandukabhaya), derived from UCSC Language Technology Research Laboratory legacy-font research. The [upstream license](https://github.com/akuruAI/pandukabhaya/blob/main/LICENSE) was checked on 2026-09-09 and is retained here. The seed did not record an upstream commit, so exact upstream revision provenance remains unspecified.

The TSV headers reference `scripts/fetch_legacy_mapping.py`; that script is not included. Do not assume the data can be regenerated using that command. Preserve the supplied files and record provenance when updating them.

## Validation and use

- Test all six examples character-for-character before enabling the converter.
- Do not assume this mapping supports DL-Manel, Malithi, or other font families. Unsupported conversion should route to OCR/review.
- Include English and mixed-language negative tests. Valid-looking Sinhala output alone does not establish correct decoding.
- Follow [CLAUDE.md](../../CLAUDE.md), especially "Legacy fonts and extraction validation".

Copy verification SHA-256 values:

```text
C0BB818D913481EA0D38ADD71AF70A9156E140CA0AF85477222450C64F43C888  fm_abhaya.tsv
82EC9F4F41A04DC5D4D318A8EAEC13E8181B913AE467DBCF991BB64874D926C7  fm_abhaya_cases.tsv
```

These hashes verify equality with the supplied seed files, not converter correctness. Keep model checkpoints, private books, uploads, and generated audio outside this folder and out of Git.
