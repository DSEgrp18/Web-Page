#!/usr/bin/env bash
# Deploy one commit of the reader to the Azure VM, and roll back if it fails.
#
#     bash deploy.sh <commit-sha>
#
# Run on the VM as `azureuser`, from the checkout at ~/swara. The workflow
# .github/workflows/deploy-azure.yml runs it through `az vm run-command`, so
# GitHub never needs SSH access to the VM and its firewall stays closed.
#
# What it does, in order:
#   1. fetches and checks out exactly <commit-sha> (detached, nothing merged);
#   2. builds the images one at a time (built together they have run Docker out
#      of memory beside a loaded voice), with the real voice when the model
#      bundle is in ~/models, the labelled placeholder tone otherwise;
#   3. starts them, and smoke-tests the API, the voice's readiness and the web
#      app from the VM itself;
#   4. records what is running in ~/deployments.log: commit, voice, image IDs
#      and the model's checksum;
#   5. on any failure, deploys the commit that was running before and says so.
#
# The last line is "DEPLOYED <sha>" only when <sha> is serving and passed its
# smoke test; the workflow treats anything else as a failed deploy.
set -euo pipefail

SHA="${1:?usage: deploy.sh <commit-sha>}"
case "$SHA" in *[!0-9a-f]* | "") echo "not a commit SHA: $SHA" >&2; exit 2 ;; esac

APP="$HOME/swara"
MODELS="$HOME/models"
LOG="$HOME/deployments.log"
PROJECT=swara

cd "$APP"
git fetch --quiet origin
git cat-file -e "${SHA}^{commit}"
PREVIOUS="$(git rev-parse HEAD)"

FILES=(-f infra/docker-compose.yml)
VOICE=placeholder
if [ -f "$MODELS/xtts_si_female/model.pth" ]; then
  export MODEL_DIR="$MODELS"
  FILES+=(-f infra/compose.voice.yml)
  VOICE=real
fi
compose() { docker compose -p "$PROJECT" "${FILES[@]}" "$@"; }

release() {
  local commit="$1"
  git checkout --quiet --detach "$commit"
  for service in api worker voice-worker web; do
    echo "== building $service at ${commit:0:7}"
    compose build --quiet "$service"
  done
  compose up -d --remove-orphans
}

# The API answers /health at once; the voice may take minutes to load and is
# reported by /readiness, which must at least answer. The web app must serve
# the front door and pass /api through to the API.
smoke() {
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null http://127.0.0.1:8000/health && break
    sleep 3
  done
  curl -fsS -o /dev/null http://127.0.0.1:8000/health
  for _ in $(seq 1 40); do
    curl -fsS -o /dev/null http://127.0.0.1:3000/ && break
    sleep 3
  done
  curl -fsS -o /dev/null http://127.0.0.1:3000/
  curl -fsS http://127.0.0.1:3000/api/readiness | grep -q '"alive":true'
}

model_checksum() {
  local model="$MODELS/xtts_si_female/model.pth"
  [ -f "$model" ] || { echo none; return; }
  # Hashing 5.6 GB takes a while; once per file is enough.
  if [ ! -f "$model.sha256" ] || [ "$model" -nt "$model.sha256" ]; then
    sha256sum "$model" | cut -d' ' -f1 > "$model.sha256"
  fi
  cat "$model.sha256"
}

record() {
  local outcome="$1"
  local images
  images="$(compose images --quiet 2>/dev/null | cut -c1-19 | sort -u | tr '\n' ' ')"
  printf '%s %s commit=%s voice=%s model=%s images=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$outcome" "$(git rev-parse HEAD)" "$VOICE" \
    "$(model_checksum)" "$images" >> "$LOG"
}

echo "== deploying ${SHA:0:7} (running: ${PREVIOUS:0:7}), voice: $VOICE"
if release "$SHA" && smoke; then
  record deployed
  echo "DEPLOYED $SHA"
  exit 0
fi

echo "== ${SHA:0:7} failed its smoke test; restoring ${PREVIOUS:0:7}" >&2
record failed
if release "$PREVIOUS" && smoke; then
  record restored
  echo "ROLLED BACK to $PREVIOUS" >&2
else
  record restore-failed
  echo "ROLLBACK FAILED: the VM needs a person" >&2
fi
exit 1
