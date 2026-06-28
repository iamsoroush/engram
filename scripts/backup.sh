#!/usr/bin/env bash
#
# backup.sh — production backup: Postgres dump (+ optional off-box copy and MinIO media mirror).
# Run from the repo root ON THE PROD HOST, with the stack up and .env.prod present. Schedule via cron:
#   0 2 * * *  cd /srv/engram && scripts/backup.sh >> /var/log/engram-backup.log 2>&1
#
# Off-box copy + media mirror require `mc` (MinIO client) on the host with two aliases configured:
#   mc alias set local    http://127.0.0.1:<minio-host-port> $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
#   mc alias set offsite  https://<arvancloud-s3-endpoint>   <key> <secret>
# Set OFFSITE_ALIAS=offsite in .env.prod to enable the off-box push (strongly recommended).
# If media already lives in ArvanCloud S3 (managed/replicated), the media mirror is unnecessary.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env.prod ] || { echo "backup: .env.prod missing" >&2; exit 1; }
set -a; . ./.env.prod; set +a

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
TS="$(date -u +%Y%m%d-%H%M%S)"
DIR="${BACKUP_DIR:-/var/backups/engram}"
mkdir -p "$DIR"
DUMP="$DIR/pg-${TS}.sql.gz"

echo "[backup] dumping Postgres -> $DUMP"
$COMPOSE exec -T postgres pg_dump -U "${POSTGRES_USER:-engram}" "${POSTGRES_DB:-engram}" | gzip > "$DUMP"
test -s "$DUMP" || { echo "[backup] ERROR: empty dump" >&2; exit 1; }

# Encrypt at rest (recommended) so an off-box / provider breach yields ciphertext, not patient data.
# Store BACKUP_ENCRYPTION_KEY SEPARATELY from the backups (e.g. a password manager) — lose it and the
# backups are unrecoverable. AES-256 via openssl (portable, no extra tooling).
ART="$DUMP"
if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt -in "$DUMP" -out "$DUMP.enc" -pass env:BACKUP_ENCRYPTION_KEY
  rm -f "$DUMP"; ART="$DUMP.enc"
  echo "[backup] encrypted -> $ART"
else
  echo "[backup] WARN: BACKUP_ENCRYPTION_KEY unset — dump stored UNENCRYPTED (set it for PHI safety)."
fi

if [ -n "${OFFSITE_ALIAS:-}" ] && command -v mc >/dev/null; then
  echo "[backup] copying dump off-box -> ${OFFSITE_ALIAS}/${OFFSITE_BUCKET}"
  mc cp "$ART" "${OFFSITE_ALIAS}/${OFFSITE_BUCKET:?set OFFSITE_BUCKET}/postgres/" || echo "[backup] WARN: off-box dump copy failed"
  # Mirror media only when using self-hosted MinIO (skip if media is already in ArvanCloud S3).
  case "${BACKEND_OBJECT_STORAGE_ENDPOINT:-}" in
    *minio*) echo "[backup] mirroring media -> ${OFFSITE_ALIAS}/${OFFSITE_BUCKET}/media"
             mc mirror --overwrite "local/${BACKEND_OBJECT_STORAGE_BUCKET:-engram-captures}" \
               "${OFFSITE_ALIAS}/${OFFSITE_BUCKET}/media" || echo "[backup] WARN: media mirror failed" ;;
  esac
else
  echo "[backup] NOTE: OFFSITE_ALIAS unset or mc missing — local-only backup (configure off-box copy!)."
fi

echo "[backup] pruning local dumps older than ${BACKUP_RETAIN_DAYS:-14}d"
find "$DIR" -name 'pg-*.sql.gz*' -mtime +"${BACKUP_RETAIN_DAYS:-14}" -delete || true
echo "[backup] done: $ART"
