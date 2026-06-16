#!/usr/bin/env bash
#
# restore.sh — restore a Postgres dump produced by backup.sh. DESTRUCTIVE.
# Run from the repo root on the prod host with the stack up and .env.prod present.
#   scripts/restore.sh /var/backups/notari/pg-YYYYMMDD-HHMMSS.sql.gz
#
# Rehearse this on a NON-prod database periodically — an untested backup is not a backup.
# Cleanest restore is into a freshly-created empty database; restoring over a live DB can
# fail on existing objects unless the dump was taken with --clean.
set -euo pipefail

cd "$(dirname "$0")/.."
DUMP="${1:?usage: restore.sh <pg-dump.sql.gz[.enc]>}"
[ -f "$DUMP" ] || { echo "restore: no such file: $DUMP" >&2; exit 1; }
[ -f .env.prod ] || { echo "restore: .env.prod missing" >&2; exit 1; }
set -a; . ./.env.prod; set +a

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
DB="${POSTGRES_DB:-notari}"; USER="${POSTGRES_USER:-notari}"

read -r -p "This OVERWRITES database '$DB' from $DUMP. Type 'yes' to proceed: " confirm
[ "$confirm" = "yes" ] || { echo "aborted."; exit 1; }

echo "[restore] loading $DUMP -> $DB"
# `.enc` dumps (from backup.sh with BACKUP_ENCRYPTION_KEY) are decrypted first; plain `.gz` load directly.
case "$DUMP" in
  *.enc)
    [ -n "${BACKUP_ENCRYPTION_KEY:-}" ] || { echo "restore: $DUMP is encrypted but BACKUP_ENCRYPTION_KEY is unset" >&2; exit 1; }
    openssl enc -d -aes-256-cbc -pbkdf2 -in "$DUMP" -pass env:BACKUP_ENCRYPTION_KEY | gunzip -c \
      | $COMPOSE exec -T postgres psql -v ON_ERROR_STOP=1 -U "$USER" -d "$DB" ;;
  *)
    gunzip -c "$DUMP" | $COMPOSE exec -T postgres psql -v ON_ERROR_STOP=1 -U "$USER" -d "$DB" ;;
esac
echo "[restore] done. Restart services if needed: $COMPOSE restart backend ai-engine"
