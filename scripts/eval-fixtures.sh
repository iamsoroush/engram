#!/usr/bin/env bash
#
# AI eval fixtures — capture media live in OBJECT STORAGE, never in git.
#
# Workflow:
#   1. ./scripts/eval-fixtures.sh stage     # create the local intake dir + expectation templates
#   2. (clinician) drop recordings into ~/notari-eval-fixtures/<job>/ per its README
#   3. ./scripts/eval-fixtures.sh push      # upload intake dir → the notari-eval-fixtures MinIO bucket
#   4. ./scripts/eval-fixtures.sh run       # score the suite against the staged fixtures
#   ./scripts/eval-fixtures.sh pull [dir]   # fetch fixtures back from object storage (teammates / CI)
#   ./scripts/eval-fixtures.sh ls           # list what's in the bucket
#
# Media + their sibling .json are mirrored under <job>/ prefixes in the bucket; nothing capture-derived
# is committed. Object storage is reached with a `minio/mc` sidecar joined to the stack's shared network
# (the ai-engine app container has no S3 client/creds by design). All settings are env-overridable.
set -euo pipefail

STAGING="${EVAL_FIXTURES_DIR:-$HOME/notari-eval-fixtures}"
BUCKET="${EVAL_FIXTURES_S3_BUCKET:-notari-eval-fixtures}"
NETWORK="${EVAL_FIXTURES_S3_NETWORK:-engram-shared}"
S3_HOST="${EVAL_FIXTURES_S3_HOST:-minio:9000}"
ACCESS_KEY="${EVAL_FIXTURES_S3_ACCESS_KEY:-engram-dev}"
SECRET_KEY="${EVAL_FIXTURES_S3_SECRET_KEY:-engram-dev-secret}"
MC_IMAGE="${EVAL_FIXTURES_MC_IMAGE:-minio/mc}"
CONTAINER="${EVAL_FIXTURES_CONTAINER:-engram-main-ai-engine-1}"
JOBS="transcription caption matching"

HERE="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$HERE/../apps/ai_engine/eval"
TEMPLATES="$EVAL_DIR/expectations"

# Run `mc <args>` in a throwaway sidecar on the stack network. Pass a host mount via $MC_MOUNT.
mc() {
  docker run --rm --network "$NETWORK" \
    -e MC_HOST_s3="http://$ACCESS_KEY:$SECRET_KEY@$S3_HOST" \
    ${MC_MOUNT:+-v "$MC_MOUNT"} "$MC_IMAGE" "$@"
}

cmd_stage() {
  for job in $JOBS; do
    mkdir -p "$STAGING/$job"
    if [ -d "$TEMPLATES/$job" ]; then
      cp -n "$TEMPLATES/$job"/*.json "$STAGING/$job/" 2>/dev/null || true
    fi
  done
  cp -f "$TEMPLATES/README.md" "$STAGING/README.md" 2>/dev/null || true
  echo "Staged intake dir at: $STAGING"
  echo "  drop recordings into <job>/ next to the matching <case>.json (see $STAGING/README.md)"
  find "$STAGING" -maxdepth 2 -type f | sort | sed "s#^$STAGING#  #"
}

cmd_push() {
  [ -d "$STAGING" ] || { echo "no intake dir at $STAGING — run 'stage' first"; exit 1; }
  MC_MOUNT="$STAGING:/data:ro" mc mb --ignore-existing "s3/$BUCKET" >/dev/null
  MC_MOUNT="$STAGING:/data:ro" mc mirror --overwrite --exclude "README.md" /data "s3/$BUCKET"
}

cmd_pull() {
  local dest="${1:-$STAGING}"
  mkdir -p "$dest"
  MC_MOUNT="$dest:/data" mc mirror --overwrite "s3/$BUCKET" /data
  echo "Pulled to: $dest"
}

cmd_ls() { mc ls --recursive "s3/$BUCKET" || true; }

# Score the suite against the staged fixtures: copy the eval code + media into the container (works
# pre-merge too, since the code is taken from THIS checkout) and run with EVAL_FIXTURES_DIR set.
cmd_run() {
  docker exec "$CONTAINER" rm -rf /tmp/evalrun
  docker cp "$EVAL_DIR/." "$CONTAINER:/tmp/evalrun/"
  [ -d "$STAGING" ] && docker cp "$STAGING/." "$CONTAINER:/tmp/evalrun/_media/"
  docker exec -e EVAL_FIXTURES_DIR=/tmp/evalrun/_media "$CONTAINER" python /tmp/evalrun/run_all.py
}

case "${1:-}" in
  stage) cmd_stage ;;
  push)  cmd_push ;;
  pull)  shift; cmd_pull "$@" ;;
  ls)    cmd_ls ;;
  run)   cmd_run ;;
  *) echo "usage: $0 {stage|push|pull [dir]|ls|run}"; exit 2 ;;
esac
