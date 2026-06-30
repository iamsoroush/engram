#!/usr/bin/env bash
#
# prepare-server.sh — production OS prep to run ON THE HOST after cloning the repo.
#
# Assumes Docker Engine + compose plugin are ALREADY installed (e.g. by your Ansible base
# playbook). Use this when the box has Docker but lacks the production-specific hardening. The
# Ansible equivalent — deploy/ansible/prepare-server.yml — does the same prep declaratively from
# your control machine; use whichever fits how the box was provisioned.
#
# Workflow:  git clone … /srv/engram  ->  scripts/prepare-server.sh  ->  scripts/bootstrap.sh
#
#   sudo scripts/prepare-server.sh
#   HARDEN_SSH=1 sudo scripts/prepare-server.sh                            # also lock down SSH
#   DOCKER_REGISTRY_MIRROR=https://<mirror> sudo scripts/prepare-server.sh # Iran image-pull fix
#
# What it does (idempotent):
#   1. Verifies Docker is installed (does NOT install it — assumed present).
#   2. Firewall (ufw): allows SSH + 80 + 443 (+443/udp) BEFORE enabling, denies other inbound.
#   3. Enables unattended security updates.
#   4. Installs + enables fail2ban.
#   5. Optional Docker registry mirror (DOCKER_REGISTRY_MIRROR) — Iran image-pull workaround.
#   6. HARDEN_SSH=1 only: disables root + password SSH login (refuses unless an SSH key exists).
#
# Tunables:
#   SSH_PORT                default: auto-detected from your live connection, fallback 22
#   DOCKER_REGISTRY_MIRROR  default: empty (skip); set to an Iranian Docker Hub mirror if pulls fail
#   HARDEN_SSH              default 0 (set 1 to lock down SSH — KEY AUTH MUST WORK FIRST)
set -euo pipefail

SUDO=""; [ "$(id -u)" -ne 0 ] && { command -v sudo >/dev/null && SUDO="sudo" || { echo "run as root or install sudo" >&2; exit 1; }; }
log()  { printf '\n\033[1;36m[prepare]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[prepare] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[prepare] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null || die "this script targets Ubuntu/Debian (apt). On another distro, set up a firewall (22/80/443) + fail2ban + auto-updates manually, then run scripts/bootstrap.sh."
export DEBIAN_FRONTEND=noninteractive

# --- 1. Docker (assumed installed) -------------------------------------------------------------
command -v docker >/dev/null || die "Docker not found — install it first (your base Ansible playbook), then re-run."
docker compose version >/dev/null 2>&1 || warn "'docker compose' plugin missing — install docker-compose-plugin before bootstrap."

detect_ssh_port() {
  if [ -n "${SSH_CONNECTION:-}" ]; then awk '{print $4}' <<<"$SSH_CONNECTION"; return; fi
  local p; p="$(grep -iE '^[[:space:]]*Port[[:space:]]+[0-9]+' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' | head -n1)"
  echo "${p:-22}"
}
SSH_PORT="${SSH_PORT:-$(detect_ssh_port)}"

# --- 2. Firewall (ufw) -------------------------------------------------------------------------
log "configuring firewall (ufw): SSH(:$SSH_PORT) + 80 + 443 in, deny other inbound"
$SUDO apt-get update -y >/dev/null
$SUDO apt-get install -y ufw >/dev/null
$SUDO ufw allow "${SSH_PORT}/tcp" >/dev/null      # detected SSH port — allowed BEFORE enabling
$SUDO ufw allow 22/tcp >/dev/null                 # belt-and-suspenders in case detection was wrong
$SUDO ufw allow 80/tcp >/dev/null                 # Caddy: ACME challenge + HTTP->HTTPS redirect
$SUDO ufw allow 443/tcp >/dev/null                # Caddy: HTTPS
$SUDO ufw allow 443/udp >/dev/null                # Caddy: HTTP/3 (QUIC)
$SUDO ufw default deny incoming >/dev/null
$SUDO ufw default allow outgoing >/dev/null
$SUDO ufw --force enable >/dev/null
log "firewall active:"; $SUDO ufw status verbose | sed 's/^/    /'
warn "ufw does not filter Docker-published ports; this stack only publishes 80/443 (Caddy) + 127.0.0.1:8080 (localhost), so that's fine."

# --- 3. Unattended security updates ------------------------------------------------------------
log "enabling unattended security updates"
$SUDO apt-get install -y unattended-upgrades >/dev/null
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
  | $SUDO tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
$SUDO systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

# --- 4. fail2ban -------------------------------------------------------------------------------
log "installing fail2ban (SSH brute-force protection)"
$SUDO apt-get install -y fail2ban >/dev/null && $SUDO systemctl enable --now fail2ban >/dev/null 2>&1 || warn "fail2ban install/enable failed (non-fatal)"

# --- 5. Docker registry mirror (Iran: Docker Hub is often blocked from Iranian IPs) ------------
if [ -n "${DOCKER_REGISTRY_MIRROR:-}" ]; then
  if [ -f /etc/docker/daemon.json ] && grep -q registry-mirrors /etc/docker/daemon.json; then
    log "Docker registry mirror already configured in /etc/docker/daemon.json"
  else
    log "configuring Docker registry mirror: $DOCKER_REGISTRY_MIRROR"
    $SUDO mkdir -p /etc/docker
    printf '{\n  "registry-mirrors": ["%s"]\n}\n' "$DOCKER_REGISTRY_MIRROR" | $SUDO tee /etc/docker/daemon.json >/dev/null
    $SUDO systemctl restart docker
  fi
else
  warn "DOCKER_REGISTRY_MIRROR unset — if 'docker compose build/pull' fails from Iran, set it (e.g. an ArvanCloud Docker mirror) or use Shecan DNS, then re-run."
fi

# --- 6. Optional SSH hardening (opt-in) --------------------------------------------------------
if [ "${HARDEN_SSH:-0}" = "1" ]; then
  has_key=0
  for f in "$HOME/.ssh/authorized_keys" /root/.ssh/authorized_keys "/home/$USER/.ssh/authorized_keys"; do
    [ -s "$f" ] && has_key=1
  done
  if [ "$has_key" != "1" ]; then
    warn "HARDEN_SSH=1 but no authorized_keys found — REFUSING to disable password login (would lock you out). Add your key first, then re-run."
  else
    log "hardening SSH: disabling root login + password authentication"
    printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\nChallengeResponseAuthentication no\n' \
      | $SUDO tee /etc/ssh/sshd_config.d/99-engram.conf >/dev/null
    $SUDO systemctl reload ssh 2>/dev/null || $SUDO systemctl reload sshd 2>/dev/null || warn "couldn't reload sshd — apply manually"
    warn "keep your current SSH session open and verify a NEW key-based login works before closing it."
  fi
fi

log "server prepared. Next:  GATEWAY_API_KEY=gw_… scripts/bootstrap.sh"
