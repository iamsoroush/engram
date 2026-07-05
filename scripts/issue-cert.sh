#!/usr/bin/env bash
#
# issue-cert.sh — obtain/renew the TLS cert for CADDY_SITE_ADDRESS via acme.sh DNS-01 (ArvanCloud
# DNS API), and install it where Caddy serves it (deploy/certs/, mounted read-only into the caddy
# container as /certs). WHY DNS-01: from Iran, Let's Encrypt's HTTP-01 / TLS-ALPN-01 multi-perspective
# validation is unreliable — some LE vantage points can't route inbound — so we prove domain control
# with a DNS TXT record instead (no inbound connection needed). Idempotent; safe to re-run.
#
# Reads from .env.prod:  ARVAN_API_KEY (an ArvanCloud API key with DNS access to the domain),
#                        CADDY_SITE_ADDRESS (the domain), optional ACME_EMAIL.
# bootstrap.sh runs this automatically before bringing the stack up, when ARVAN_API_KEY is set.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
[ -f .env.prod ] || { echo "issue-cert: .env.prod missing" >&2; exit 1; }
set -a; . ./.env.prod; set +a

: "${ARVAN_API_KEY:?set ARVAN_API_KEY in .env.prod (ArvanCloud API key with DNS access to the domain)}"
DOMAIN="${CADDY_SITE_ADDRESS:?set CADDY_SITE_ADDRESS in .env.prod}"
CERTDIR="$REPO_ROOT/deploy/certs"
ACME="$HOME/.acme.sh/acme.sh"
mkdir -p "$CERTDIR"

if [ ! -f "$ACME" ]; then
  echo "[issue-cert] installing acme.sh"
  curl -s https://get.acme.sh | sh -s email="${ACME_EMAIL:-admin@$DOMAIN}" >/dev/null
fi
"$ACME" --set-default-ca --server letsencrypt >/dev/null 2>&1 || true

# acme.sh's ArvanCloud DNS plugin expects the "Apikey <key>" header value.
export Arvan_Token="Apikey $ARVAN_API_KEY"

if [ ! -s "$CERTDIR/$DOMAIN.crt" ] && ! "$ACME" --list 2>/dev/null | awk '{print $1}' | grep -qx "$DOMAIN"; then
  echo "[issue-cert] issuing cert for $DOMAIN via DNS-01 (Arvan)"
  "$ACME" --issue --dns dns_arvan -d "$DOMAIN" --server letsencrypt --dnssleep 30
fi

# (Re)install to the Caddy-mounted path + register the renewal reload hook. On a fresh box the caddy
# container isn't up yet, so the reload no-ops now; acme.sh's cron reload keeps it fresh thereafter.
echo "[issue-cert] installing cert to $CERTDIR + registering reload hook"
"$ACME" --install-cert -d "$DOMAIN" --ecc \
  --fullchain-file "$CERTDIR/$DOMAIN.crt" \
  --key-file "$CERTDIR/$DOMAIN.key" \
  --reloadcmd "docker exec engram-caddy-1 caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || docker restart engram-caddy-1 >/dev/null 2>&1 || true"

echo "[issue-cert] done — cert at $CERTDIR/$DOMAIN.{crt,key} (acme.sh auto-renews via cron)"
