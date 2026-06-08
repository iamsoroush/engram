#!/usr/bin/env bash
#
# dev-stack.sh — run an isolated AesMem app stack for the current checkout.
#
# Shared Postgres + MinIO (docker-compose.shared-infra.yml) are started once and
# reused. Each git worktree gets its own database (cloned from the canonical `aesmem`
# DB) and its own bucket (mirrored from `aesmem-captures`), plus its own backend /
# ai-engine / frontend / redis containers on unique host ports. The main checkout runs
# the canonical stack (database `aesmem`, the clone source for every worktree).
#
# Usage (run from inside the checkout you want to launch — main repo or a worktree):
#   scripts/dev-stack.sh up            # provision + start this stack
#   scripts/dev-stack.sh down          # stop this stack's containers (keep its data)
#   scripts/dev-stack.sh down --data   # also drop this worktree's database + bucket
#   scripts/dev-stack.sh refresh       # re-clone DB + re-mirror media from main, restart
#   scripts/dev-stack.sh status        # list running stacks + this stack's URLs
#   scripts/dev-stack.sh infra-up      # start shared Postgres + MinIO only
#   scripts/dev-stack.sh infra-down    # stop shared infra (keeps volumes/data)
#
# The script may be invoked by absolute path from anywhere; it locates the main repo
# from its own location and the target checkout from your current directory.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INFRA_PROJECT="aesmem-infra"
INFRA_FILE="$MAIN_ROOT/docker-compose.shared-infra.yml"
APP_FILE="$MAIN_ROOT/docker-compose.app.yml"

PGUSER="${POSTGRES_USER:-aesmem}"
MINIO_USER="${MINIO_ROOT_USER:-aesmem-dev}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-aesmem-dev-secret}"

CANONICAL_DB="aesmem"
CANONICAL_BUCKET="aesmem-captures"

# Target checkout = git toplevel of the current directory.
WT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$WT" ]]; then
  echo "error: run this from inside the AesMem git checkout you want to launch." >&2
  exit 1
fi

# A linked worktree has a git-dir that differs from the common git-dir.
GIT_DIR="$(cd "$WT" && git rev-parse --absolute-git-dir)"
GIT_COMMON="$(cd "$WT" && git rev-parse --path-format=absolute --git-common-dir)"
if [[ "$GIT_DIR" == "$GIT_COMMON" ]]; then
  IS_WORKTREE=0
  SLUG="main"
  STACK_DB="$CANONICAL_DB"
  STACK_BUCKET="$CANONICAL_BUCKET"
  PROJECT="aesmem-main"
else
  IS_WORKTREE=1
  BRANCH="$(cd "$WT" && git rev-parse --abbrev-ref HEAD)"
  SLUG="$(printf '%s' "$BRANCH" | tr '[:upper:]/' '[:lower:]_' | tr -cd 'a-z0-9_' | cut -c1-24)"
  [[ -n "$SLUG" ]] || SLUG="$(basename "$WT" | tr -cd 'a-z0-9_')"
  STACK_DB="aesmem_${SLUG}"
  STACK_BUCKET="aesmem-captures-${SLUG}"
  PROJECT="aesmem_${SLUG}"
fi

ENV_FILE="$WT/.env"

infra_pg()  { docker compose -p "$INFRA_PROJECT" -f "$INFRA_FILE" exec -T postgres "$@"; }
infra_mc()  { docker compose -p "$INFRA_PROJECT" -f "$INFRA_FILE" exec -T minio mc "$@"; }
app_compose() { docker compose -p "$PROJECT" --project-directory "$WT" --env-file "$ENV_FILE" -f "$APP_FILE" "$@"; }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '\033[1;36m[dev-stack]\033[0m %s\n' "$*"; }

port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1 && { exec 3>&- 3<&-; return 0; } || return 1; }

# Frontend/backend ports pinned by OTHER checkouts (main + other worktrees, never this one).
other_ports() {
  { [[ -f "$MAIN_ROOT/.env" ]] && cat "$MAIN_ROOT/.env"
    for f in "$MAIN_ROOT/.claude/worktrees"/*/.env; do
      [[ -f "$f" && "$f" != "$ENV_FILE" ]] && cat "$f"
    done; } 2>/dev/null \
    | grep -E '^(FRONTEND_PORT|BACKEND_PORT)=' | cut -d= -f2 | tr -d ' "' || true
}

# pick_port BASE TAKEN — lowest port >= BASE that is free and not in the TAKEN list.
pick_port() {
  local candidate="$1" taken="$2"
  while port_in_use "$candidate" || grep -qx "$candidate" <<<"$taken"; do
    candidate=$((candidate + 1))
  done
  printf '%s' "$candidate"
}

set_env_var() { # FILE KEY VALUE — update in place or append.
  local file="$1" key="$2" val="$3"
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    # portable in-place edit without GNU sed -i quirks
    local tmp; tmp="$(mktemp)"
    grep -vE "^${key}=" "$file" > "$tmp"
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
    mv "$tmp" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
  fi
}

get_env_var() { grep -E "^$2=" "$1" 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' "'; }

# ---------------------------------------------------------------------------
# Shared infra
# ---------------------------------------------------------------------------
infra_up() {
  log "Starting shared infra (Postgres + MinIO)…"
  docker compose -p "$INFRA_PROJECT" -f "$INFRA_FILE" up -d
  log "Waiting for Postgres to be healthy…"
  until infra_pg pg_isready -U "$PGUSER" -d "$CANONICAL_DB" >/dev/null 2>&1; do sleep 1; done
  log "Shared infra ready."
}

infra_down() { docker compose -p "$INFRA_PROJECT" -f "$INFRA_FILE" down; }

# ---------------------------------------------------------------------------
# Per-stack database + bucket
# ---------------------------------------------------------------------------
db_exists() { infra_pg psql -U "$PGUSER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$1'" 2>/dev/null | grep -q 1; }

ensure_db() {
  if db_exists "$STACK_DB"; then
    log "Database '$STACK_DB' already exists (leaving its data untouched)."
    return
  fi
  log "Creating database '$STACK_DB'…"
  infra_pg psql -U "$PGUSER" -d postgres -c "CREATE DATABASE \"$STACK_DB\"" >/dev/null
  if [[ "$IS_WORKTREE" == "1" ]] && db_exists "$CANONICAL_DB"; then
    log "Cloning data from '$CANONICAL_DB' → '$STACK_DB'…"
    infra_pg sh -c "pg_dump -U $PGUSER -d $CANONICAL_DB --no-owner --no-privileges | psql -q -U $PGUSER -d $STACK_DB" >/dev/null
    log "Clone complete. (Your branch's new migrations apply on top via 'alembic upgrade head'.)"
  fi
}

ensure_bucket() {
  infra_mc alias set local "http://localhost:9000" "$MINIO_USER" "$MINIO_PASS" >/dev/null 2>&1 || true
  if infra_mc ls "local/$STACK_BUCKET" >/dev/null 2>&1; then
    log "Bucket '$STACK_BUCKET' already exists."
    return
  fi
  log "Creating bucket '$STACK_BUCKET'…"
  infra_mc mb "local/$STACK_BUCKET" >/dev/null 2>&1 || true
  if [[ "$IS_WORKTREE" == "1" ]]; then
    log "Mirroring media '$CANONICAL_BUCKET' → '$STACK_BUCKET'…"
    infra_mc mirror --overwrite --quiet "local/$CANONICAL_BUCKET" "local/$STACK_BUCKET" >/dev/null 2>&1 || true
  fi
}

drop_data() {
  if [[ "$IS_WORKTREE" != "1" ]]; then
    echo "refusing to drop the canonical '$CANONICAL_DB' database / bucket." >&2
    exit 1
  fi
  log "Dropping database '$STACK_DB' and bucket '$STACK_BUCKET'…"
  infra_pg psql -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS \"$STACK_DB\" WITH (FORCE)" >/dev/null || true
  infra_mc rb --force "local/$STACK_BUCKET" >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# .env materialisation
# ---------------------------------------------------------------------------
ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$WT/.env.example" ]]; then cp "$WT/.env.example" "$ENV_FILE"; else : > "$ENV_FILE"; fi
  fi

  local fport bport taken
  if [[ "$IS_WORKTREE" == "1" ]]; then
    # Reuse this worktree's pinned ports, but only if they don't collide with another
    # checkout (this rejects the 5183/8010 defaults inherited from .env.example).
    taken="$(other_ports)"
    fport="$(get_env_var "$ENV_FILE" FRONTEND_PORT)"
    if [[ -z "$fport" ]] || grep -qx "$fport" <<<"$taken"; then fport="$(pick_port 5184 "$taken")"; fi
    taken="$taken"$'\n'"$fport"
    bport="$(get_env_var "$ENV_FILE" BACKEND_PORT)"
    if [[ -z "$bport" ]] || grep -qx "$bport" <<<"$taken"; then bport="$(pick_port $((fport + 2827)) "$taken")"; fi
  else
    fport=5183; bport=8010
  fi

  set_env_var "$ENV_FILE" COMPOSE_PROJECT_NAME "$PROJECT"
  set_env_var "$ENV_FILE" FRONTEND_PORT "$fport"
  set_env_var "$ENV_FILE" BACKEND_PORT "$bport"
  set_env_var "$ENV_FILE" STACK_DB "$STACK_DB"
  set_env_var "$ENV_FILE" STACK_BUCKET "$STACK_BUCKET"
  set_env_var "$ENV_FILE" VITE_API_URL "/api/v1"
  set_env_var "$ENV_FILE" BACKEND_CORS_ORIGINS "[\"http://localhost:${fport}\"]"
  # Keep .env consistent with the per-stack DB/bucket (override any value copied from
  # .env.example). Compose derives the DB from STACK_DB regardless; these are for clarity.
  set_env_var "$ENV_FILE" BACKEND_DATABASE_URL "postgresql+psycopg://aesmem:aesmem@postgres:5432/${STACK_DB}"
  set_env_var "$ENV_FILE" BACKEND_OBJECT_STORAGE_BUCKET "$STACK_BUCKET"
  FRONTEND_PORT_RESOLVED="$fport"; BACKEND_PORT_RESOLVED="$bport"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_up() {
  infra_up
  ensure_db
  ensure_bucket
  ensure_env
  log "Building + starting '$PROJECT' (frontend:$FRONTEND_PORT_RESOLVED backend:$BACKEND_PORT_RESOLVED db:$STACK_DB)…"
  app_compose up -d --build
  echo
  log "Stack '$PROJECT' is up:"
  echo "    app      → http://localhost:${FRONTEND_PORT_RESOLVED}"
  echo "    api docs → http://localhost:${BACKEND_PORT_RESOLVED}/docs"
  echo "    database → ${STACK_DB}   bucket → ${STACK_BUCKET}   (shared MinIO console http://localhost:9011)"
}

cmd_down() {
  local data=0
  [[ "${1:-}" == "--data" ]] && data=1
  log "Stopping '$PROJECT'…"
  app_compose down --volumes || true
  [[ "$data" == "1" ]] && drop_data || true
}

cmd_refresh() {
  [[ "$IS_WORKTREE" == "1" ]] || { echo "refresh only applies to worktree stacks." >&2; exit 1; }
  drop_data
  ensure_db
  ensure_bucket
  app_compose restart backend ai-engine || app_compose up -d
  log "Re-seeded '$STACK_DB' from '$CANONICAL_DB' and restarted."
}

cmd_status() {
  log "Running stacks:"
  docker compose ls || true
  echo
  if [[ -f "$ENV_FILE" ]]; then
    log "This checkout → project '$PROJECT'"
    echo "    app  http://localhost:$(get_env_var "$ENV_FILE" FRONTEND_PORT)"
    echo "    api  http://localhost:$(get_env_var "$ENV_FILE" BACKEND_PORT)/docs"
    echo "    db   $(get_env_var "$ENV_FILE" STACK_DB)    bucket $(get_env_var "$ENV_FILE" STACK_BUCKET)"
  fi
}

case "${1:-}" in
  up)         cmd_up ;;
  down)       cmd_down "${2:-}" ;;
  refresh)    cmd_refresh ;;
  status)     cmd_status ;;
  infra-up)   infra_up ;;
  infra-down) infra_down ;;
  *) sed -n '3,20p' "${BASH_SOURCE[0]}"; exit 1 ;;
esac
