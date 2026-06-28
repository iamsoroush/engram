#!/usr/bin/env bash
#
# gen-secrets.sh — generate strong production secrets for .env.prod.
# Prints ready-to-paste lines. Run ONCE per environment; store the result securely and
# NEVER commit .env.prod. Re-running generates NEW values (which would invalidate existing
# sessions / break access to already-encrypted data) — only do that for a deliberate rotation.
#
#   scripts/gen-secrets.sh                # print to stdout
#   scripts/gen-secrets.sh >> .env.prod   # append (then fill the non-secret vars by hand)
set -euo pipefail

command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

# URL/shell-safe token (no +/=) for passwords used in connection strings.
safe() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-"${1:-40}"; }

PG_PASS="$(safe 40)"

cat <<EOF
# --- generated $(date -u +%Y-%m-%dT%H:%M:%SZ) — paste into .env.prod, then keep secret ---
POSTGRES_PASSWORD=${PG_PASS}
MINIO_ROOT_PASSWORD=$(safe 40)
BACKEND_JWT_SECRET=$(openssl rand -hex 48)
AI_ENGINE_INTERNAL_TOKEN=$(openssl rand -hex 32)
GRAFANA_ADMIN_PASSWORD=$(safe 32)
GLITCHTIP_SECRET_KEY=$(openssl rand -hex 48)
GLITCHTIP_POSTGRES_PASSWORD=$(safe 40)
BACKUP_ENCRYPTION_KEY=$(safe 48)
# Remember to update BACKEND_DATABASE_URL to use the POSTGRES_PASSWORD above:
#   BACKEND_DATABASE_URL=postgresql+psycopg://engram:${PG_PASS}@postgres:5432/engram
# And create an APP-SCOPED object-storage key (not the MinIO root) for
#   BACKEND_OBJECT_STORAGE_ACCESS_KEY / _SECRET_KEY  (see docs/production.md).
EOF
