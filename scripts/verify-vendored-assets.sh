#!/usr/bin/env bash
#
# Verify the vendored FM-Abhaya legacy font tables against the SHA-256 values
# recorded in data/legacy_fonts/README.md.
#
# These tables are third-party data (akuruAI/Pandukabhaya, MIT) that the future
# legacy-font decoder depends on character-for-character. A silent edit, an
# accidental line-ending normalisation, or a partial re-copy would change
# decoding behaviour without any obvious diff, so the recorded hashes are the
# authority and this check is the guard.
#
# The hashes prove the files match what was supplied. They do not establish that
# the mapping itself is correct; that requires the conversion cases and human
# review described in CLAUDE.md.
#
# Usage: scripts/verify-vendored-assets.sh
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
fonts_dir="${repo_root}/data/legacy_fonts"
readme="${fonts_dir}/README.md"
status=0

if [[ ! -f "${readme}" ]]; then
  echo "FAIL: ${readme} is missing; provenance cannot be verified." >&2
  exit 1
fi

for file in fm_abhaya.tsv fm_abhaya_cases.tsv; do
  path="${fonts_dir}/${file}"

  if [[ ! -f "${path}" ]]; then
    echo "FAIL: ${file} is missing from data/legacy_fonts/." >&2
    status=1
    continue
  fi

  # The README records hashes as "<sha256>  <filename>" inside a code block.
  mapfile -t expected < <(
    grep -oiE "^[0-9a-f]{64}[[:space:]]+\*?${file}\$" "${readme}" \
      | awk '{ print tolower($1) }'
  )

  if [[ "${#expected[@]}" -ne 1 ]]; then
    echo "FAIL: expected exactly one recorded hash for ${file} in README.md, found ${#expected[@]}." >&2
    status=1
    continue
  fi

  actual="$(sha256sum "${path}" | awk '{ print tolower($1) }')"

  if [[ "${actual}" != "${expected[0]}" ]]; then
    echo "FAIL: ${file} does not match its recorded hash." >&2
    echo "  expected ${expected[0]}" >&2
    echo "  actual   ${actual}" >&2
    echo "  If this change is intentional, update README.md and record the new" >&2
    echo "  upstream provenance in the same commit." >&2
    status=1
    continue
  fi

  echo "OK: ${file} matches its recorded hash."
done

# The README documents six supplied legacy-input/expected-Unicode examples.
# Losing one would silently weaken the decoder's acceptance tests.
cases="${fonts_dir}/fm_abhaya_cases.tsv"
if [[ -f "${cases}" ]]; then
  case_count="$(grep -cvE '^[[:space:]]*(#|$)' "${cases}" || true)"
  if [[ "${case_count}" -ne 6 ]]; then
    echo "FAIL: expected 6 conversion cases in fm_abhaya_cases.tsv, found ${case_count}." >&2
    status=1
  else
    echo "OK: 6 conversion cases present."
  fi
fi

exit "${status}"
