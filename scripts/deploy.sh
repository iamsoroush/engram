#!/usr/bin/env bash
#
# deploy.sh — production deploy for the TLS stack. Run from the repo root on the prod host.
#   scripts/deploy.sh
# Pulls main, rebuilds, applies DB migrations (the backend runs `alembic upgrade head` on start),
# brings up the prod + TLS overlay, and waits for the backend to report healthy.
#
# Rollback: `git checkout <previous-good-tag/sha> && scripts/deploy.sh`. The DB schema migrates
# FORWARD on deploy — a code rollback past a migration needs a matching DB restore (scripts/restore.sh).
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env.prod ] || { echo "deploy: .env.prod missing — cp .env.prod.example .env.prod, then scripts/gen-secrets.sh" >&2; exit 1; }

FILES="-f docker-compose.prod.yml -f docker-compose.prod.tls.yml"
COMPOSE="docker compose $FILES --env-file .env.prod"

echo "[deploy] git pull --ff-only"
git pull --ff-only

echo "[deploy] build + up (migrations run on backend start)"
$COMPOSE up -d --build

echo "[deploy] waiting for backend health…"
ok=0
for _ in $(seq 1 40); do
  if docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend \
       python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=5)" >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 3
done
[ "$ok" = 1 ] && echo "[deploy] backend healthy" || { echo "[deploy] ERROR: backend not healthy — check: $COMPOSE logs backend" >&2; exit 1; }

$COMPOSE ps
echo "[deploy] done. Verify externally: curl -I https://<your-domain>/api/v1/health"
