#!/usr/bin/env bash
#
# Guard the repository against content that must never enter Git history:
# model checkpoints, speaker reference audio, generated audio, uploaded or
# private documents, and secret material.
#
# CLAUDE.md requires the Sinhala XTTS bundle and all private documents to be
# delivered out of band and mounted at runtime. Git history is effectively
# permanent and this repository is public, so a single accidental commit is
# expensive to undo and impossible to fully retract. This check runs in CI on
# every pull request and can be run locally before pushing.
#
# Usage:
#   scripts/verify-repo-hygiene.sh
#   MAX_TRACKED_BYTES=1048576 scripts/verify-repo-hygiene.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# 5 MiB. Every legitimate source, config, and documentation file is far below
# this; weights, audio, and scanned PDFs are far above it.
max_bytes="${MAX_TRACKED_BYTES:-5242880}"
status=0

# Glob patterns that must never be tracked, with the reason reported on failure.
forbidden_globs=(
  '*.pth:model checkpoint'
  '*.pt:model checkpoint'
  '*.ckpt:model checkpoint'
  '*.safetensors:model weights'
  '*.bin:opaque binary; use an explicit, reviewed exception if genuinely needed'
  '*.wav:audio; speaker reference and generated audio stay out of Git'
  '*.mp3:generated audio'
  '*.ogg:generated audio'
  '*.flac:audio'
  '*.pdf:document; uploaded books and private documents stay out of Git'
  '*.pem:private key material'
  '.env:secret environment file'
  '.env.*:secret environment file'
)

echo "== Forbidden file types =="
for entry in "${forbidden_globs[@]}"; do
  glob="${entry%%:*}"
  reason="${entry#*:}"

  # ':(glob)' keeps the pattern matching at any depth without shell expansion.
  mapfile -t hits < <(git ls-files -- ":(glob)**/${glob}" ":(glob)${glob}")

  # .env.example and .env.<env>.example are committed templates by design.
  filtered=()
  for hit in "${hits[@]:-}"; do
    [[ -z "${hit}" ]] && continue
    [[ "${hit}" == *.example ]] && continue
    filtered+=("${hit}")
  done

  if [[ "${#filtered[@]}" -gt 0 ]]; then
    for hit in "${filtered[@]}"; do
      echo "FAIL: ${hit} is tracked (${reason})." >&2
    done
    status=1
  fi
done
[[ "${status}" -eq 0 ]] && echo "OK: no forbidden file types are tracked."

echo "== Tracked file sizes =="
oversized=0
while IFS= read -r -d '' file; do
  [[ -f "${file}" ]] || continue
  size="$(wc -c <"${file}")"
  if [[ "${size}" -gt "${max_bytes}" ]]; then
    echo "FAIL: ${file} is ${size} bytes, over the ${max_bytes}-byte limit." >&2
    oversized=1
  fi
done < <(git ls-files -z)

if [[ "${oversized}" -eq 1 ]]; then
  echo "Large artifacts belong in object storage, not Git. If a large file is" >&2
  echo "genuinely required, raise the limit deliberately in this script." >&2
  status=1
else
  echo "OK: no tracked file exceeds ${max_bytes} bytes."
fi

echo "== Ignore rules =="
for path in models/ data/uploads/ generated_audio/ .env; do
  if ! git check-ignore -q "${path}" 2>/dev/null; then
    echo "FAIL: ${path} is not covered by .gitignore." >&2
    status=1
  fi
done
[[ "${status}" -eq 0 ]] && echo "OK: model, upload, audio, and secret paths are ignored."

exit "${status}"
