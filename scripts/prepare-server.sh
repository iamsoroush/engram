#!/usr/bin/env bash
#
# prepare-server.sh — one-time OS prep for an Engram production host (Ubuntu/Debian).
#
# Workflow:  git clone … /srv/engram  ->  scripts/prepare-server.sh  ->  scripts/bootstrap.sh
#
# Idempotent. Run on a fresh VPS as root, or as a sudo-capable user:
#   sudo scripts/prepare-server.sh
#   # optionally also lock down SSH (only once key-based login works — see warning):
#   HARDEN_SSH=1 sudo scripts/prepare-server.sh
#
# What it does:
#   1. Installs Docker Engine + the compose plugin (if missing) and enables the service.
#   2. Firewall (ufw): allows SSH + 80 + 443 (+443/udp HTTP/3), denies all other inbound, enables it.
#      SSH is allowed BEFORE enabling so you cannot lock yourself out; the SSH port is auto-detected.
#   3. Enables unattended security updates.
#   4. Installs + enables fail2ban (SSH brute-force protection).
#   5. HARDEN_SSH=1 only: disables root login + password auth (refuses unless an SSH key is present).
#
# Tunables:
#   SSH_PORT        default: auto-detected from your live connection, fallback 22
#   INSTALL_DOCKER  default 1 (set 0 to skip)
#   HARDEN_SSH      default 0 (set 1 to disable root+password SSH login — KEY AUTH MUST WORK FIRST)
set -euo pipefail

SUDO=""; [ "$(id -u)" -ne 0 ] && { command -v sudo >/dev/null && SUDO="sudo" || { echo "run as root or install sudo" >&2; exit 1; }; }
log()  { printf '\n\033[1;36m[prepare]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[prepare] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[prepare] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null || die "this script targets Ubuntu/Debian (apt). On another distro, set up Docker + a firewall (allow 22/80/443) manually, then run scripts/bootstrap.sh."
export DEBIAN_FRONTEND=noninteractive

detect_ssh_port() {
  if [ -n "${SSH_CONNECTION:-}" ]; then awk '{print $4}' <<<"$SSH_CONNECTION"; return; fi
  local p; p="$(grep -iE '^[[:space:]]*Port[[:space:]]+[0-9]+' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' | head -n1)"
  echo "${p:-22}"
}
SSH_PORT="${SSH_PORT:-$(detect_ssh_port)}"

# --- 1. Docker ---------------------------------------------------------------------------------
if [ "${INSTALL_DOCKER:-1}" != "0" ] && ! command -v docker >/dev/null; then
  log "installing Docker Engine + compose plugin (get.docker.com)"
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker
  if [ "$(id -u)" -ne 0 ]; then
    $SUDO usermod -aG docker "$USER"
    warn "added '$USER' to the 'docker' group — log out/in (or run 'newgrp docker') before bootstrap, or run bootstrap with sudo."
  fi
else
  log "Docker present (or install skipped)"
fi

# --- 2. Firewall (ufw) -------------------------------------------------------------------------
log "configuring firewall (ufw): SSH(:$SSH_PORT) + 80 + 443 in, deny other inbound"
$SUDO apt-get update -y >/dev/null
$SUDO apt-get install -y ufw >/dev/null
$SUDO ufw allow "${SSH_PORT}/tcp" >/dev/null      # the detected SSH port — allow BEFORE enabling
$SUDO ufw allow 22/tcp >/dev/null                 # belt-and-suspenders in case detection was wrong
$SUDO ufw allow 80/tcp >/dev/null                 # Caddy: ACME challenge + HTTP->HTTPS redirect
$SUDO ufw allow 443/tcp >/dev/null                # Caddy: HTTPS
$SUDO ufw allow 443/udp >/dev/null                # Caddy: HTTP/3 (QUIC)
$SUDO ufw default deny incoming >/dev/null
$SUDO ufw default allow outgoing >/dev/null
$SUDO ufw --force enable >/dev/null
log "firewall active:"; $SUDO ufw status verbose | sed 's/^/    /'
warn "ufw does not filter Docker-published ports; this stack only publishes 80/443 (Caddy) and 127.0.0.1:8080 (frontend, localhost-only), so that's fine."

# --- 3. Unattended security updates ------------------------------------------------------------
log "enabling unattended security updates"
$SUDO apt-get install -y unattended-upgrades >/dev/null
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
  | $SUDO tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
$SUDO systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

# --- 4. fail2ban -------------------------------------------------------------------------------
log "installing fail2ban (SSH brute-force protection)"
$SUDO apt-get install -y fail2ban >/dev/null && $SUDO systemctl enable --now fail2ban >/dev/null 2>&1 || warn "fail2ban install/enable failed (non-fatal)"

# --- 5. Optional SSH hardening (opt-in) --------------------------------------------------------
if [ "${HARDEN_SSH:-0}" = "1" ]; then
  has_key=0
  for f in "$HOME/.ssh/authorized_keys" /root/.ssh/authorized_keys "/home/$USER/.ssh/authorized_keys"; do
    [ -s "$f" ] && has_key=1
  done
  if [ "$has_key" != "1" ]; then
    warn "HARDEN_SSH=1 but no authorized_keys found — REFUSING to disable password login (would lock you out). Add your SSH key first, then re-run."
  else
    log "hardening SSH: disabling root login + password authentication"
    printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\nChallengeResponseAuthentication no\n' \
      | $SUDO tee /etc/ssh/sshd_config.d/99-engram.conf >/dev/null
    $SUDO systemctl reload ssh 2>/dev/null || $SUDO systemctl reload sshd 2>/dev/null || warn "couldn't reload sshd — apply manually"
    warn "keep your current SSH session open and verify a NEW key-based login works before closing it."
  fi
fi

log "server prepared. Next:  GATEWAY_API_KEY=gw_… scripts/bootstrap.sh"
