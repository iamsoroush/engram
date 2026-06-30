# Ansible — production server prep

Declarative OS prep for an Engram production host (Ubuntu/Debian). The twin of
`scripts/prepare-server.sh` — same actions, run from your control machine instead of on the box.

**Assumes Docker Engine + the compose plugin are already installed** (e.g. by your base playbook).
It does *not* install Docker; it adds the production-specific hardening:

- firewall (ufw): SSH + 80 + 443 (+443/udp) allowed, all other inbound denied;
- unattended security updates;
- fail2ban;
- optional Docker registry mirror (Iran image-pull workaround);
- optional SSH lockdown (disable root + password login).

## Use

```sh
cp inventory.ini my-inventory.ini   # then set ansible_host / ansible_user
ansible-playbook -i my-inventory.ini prepare-server.yml

# with options:
ansible-playbook -i my-inventory.ini prepare-server.yml \
  -e docker_registry_mirror=https://<mirror> \
  -e harden_ssh=true            # only once key-based login works
```

Then bring up the app on the host:

```sh
cd /srv/engram && GATEWAY_API_KEY=gw_… scripts/bootstrap.sh
```

Only `ansible.builtin` modules are used, so no extra Galaxy collections are required.

## Full workflow

1. (bare server) install Docker — your base playbook, or any method.
2. `ansible-playbook -i … prepare-server.yml` — firewall + hardening.
3. on the host: `scripts/bootstrap.sh` — `.env.prod` + deploy + nightly backups (+ optional restore).

See [../../docs/production.md](../../docs/production.md) for the full picture.
