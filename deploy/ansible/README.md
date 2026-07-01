# Ansible — production server prep

Prep an Engram production host (Ubuntu 24.04) from your control machine. Iran-aware: **no
`download.docker.com`, no GitHub** — Docker installs from Ubuntu's repo via the ArvanCloud mirror,
and images pull through the ArvanCloud registry mirror.

## `setup-production.yml` — the one you want (bare box → ready)

Self-contained minimal setup: ArvanCloud apt mirror, Docker (`docker.io` + compose + buildx),
ArvanCloud Docker registry mirror, `ubuntu` in the docker group, ufw firewall (22/80/443), and a 4 GB
swapfile. Assumes the box already has a working DNS resolver.

```sh
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/setup-production.yml
```

Then **reconnect** (so the `docker` group applies) and bring the app up:

```sh
cd <repo> && GATEWAY_API_KEY=gw_... scripts/bootstrap.sh
```

Targets host `engram` (your `~/.ssh/config` alias) as user `ubuntu` — see `inventory.ini`. Uses only
`ansible.builtin` modules (no Galaxy collections). Passwordless `sudo` on the box is assumed; if not,
add `--ask-become-pass`.

## The others (`prepare-server.yml` / `scripts/prepare-server.sh`)

Older variants that **assume Docker is already installed** and only add hardening (firewall,
unattended-upgrades, fail2ban, optional SSH lockdown). Use `setup-production.yml` for a bare box; reach
for these only when Docker was already provisioned by another playbook.

See [../../docs/production.md](../../docs/production.md) for the full deployment picture.
