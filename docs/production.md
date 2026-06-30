# Production

## Current Production Shape

Production uses:

```text
docker-compose.prod.yml
```

Services:

- `frontend`: nginx serving the built Vite app and proxying `/api/v1` to backend.
- `backend`: FastAPI/uvicorn service private to the Docker network.
- `ai-engine`: background capture processing worker private to the Docker network.
- `redis`: broker/result backend for Celery.
- `postgres`: metadata store for backend v2.
- `minio`: S3-compatible object storage for backend v2.

Only the frontend/nginx service is published to the host. The backend is reachable inside Docker as:

```text
http://backend:8000
```

## API Routing

In production, leave `PROD_VITE_API_URL` empty for the default same-origin setup. The browser calls:

```text
/api/v1/...
```

nginx proxies those requests to the backend container. This avoids CORS issues and avoids phone/LAN problems where `localhost` would refer to the client device.

## Capture Storage

Production Compose defines:

```text
capture_data:/data/captures
```

This is acceptable for prototype deployments but not enough for real clinical production. For production-grade durability, move source files to object storage and metadata to a database.

Backend v2 target:

- Postgres stores tenants, users, patients, sessions, captures, artifacts, audit events, and processing job rows.
- MinIO stores source files and generated artifacts.
- MinIO remains the production object storage target; do not switch production back to backend-local files.
- Celery and Redis own background job execution. Current capture processors are placeholders until real AI logic is implemented.

## Data Safety

The product promise is that captures are not lost because the network is slow.

Current safety layers:

- Browser IndexedDB pending outbox before upload.
- Retry mechanism for failed uploads.
- Browser warning while unsynced captures exist.
- Backend-mounted volume after upload succeeds.
- Synced browser cache for fast preview, evictable after backend safety.

Backend v2 safety boundary:

- A capture is safely transferred only after the source object exists in MinIO and its metadata is committed in Postgres.
- If either side fails, the API must not return successful upload.
- Browser pending outbox data remains the safety copy until backend success.

Important distinction:

- Unsynced browser outbox data is the safety copy and must not be silently deleted.
- Synced browser cache is only a convenience and may be evicted.

## HTTPS Requirement

Real deployment should use HTTPS. This is especially important for:

- microphone access through `MediaRecorder`;
- camera access in some browser/device combinations;
- protected clinical data in transit;
- service worker/offline capabilities if added later.

For local LAN testing over HTTP, audio capture may fall back to file input.

## Environment Variables

Backend:

```sh
BACKEND_APP_NAME=Engram API
BACKEND_CORS_ORIGINS=["https://engram.example.com"]
BACKEND_AUTH_MODE=production
BACKEND_DATABASE_URL=postgresql+psycopg://...
BACKEND_OBJECT_STORAGE_ENDPOINT=https://minio.internal:9000
BACKEND_OBJECT_STORAGE_BUCKET=engram-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=...
BACKEND_OBJECT_STORAGE_SECRET_KEY=...
BACKEND_OBJECT_STORAGE_SECURE=true
BACKEND_CELERY_BROKER_URL=redis://redis:6379/0
BACKEND_CELERY_RESULT_BACKEND=redis://redis:6379/1
BACKEND_AI_JOB_MAX_RETRIES=3
BACKEND_AI_JOB_RETRY_DELAY_SECONDS=30
AI_ENGINE_INTERNAL_TOKEN=...
```

Frontend production build:

```sh
PROD_FRONTEND_PORT=80
PROD_VITE_API_URL=
```

Leave `PROD_VITE_API_URL` empty when nginx proxies `/api/v1` on the same origin.

## Operational Concerns

Before handling real clinical data, production needs:

- TLS termination and secure headers;
- authentication and role-based authorization;
- tenant/clinic isolation;
- encrypted Postgres and MinIO storage;
- backups and restore drills;
- audit logging;
- file retention policy;
- upload size limits;
- monitoring for failed uploads, failed/retried Celery jobs, Redis health, Postgres capacity, and MinIO capacity;
- structured logs and request IDs;
- migration path from file-backed prototype data to database/object storage.

## MinIO Security

Production MinIO requirements:

- Keep MinIO API and console on a private network.
- Do not enable public bucket access.
- Use separate backend app and operational admin credentials.
- Limit backend credentials to required buckets and prefixes.
- Enable server-side encryption.
- Use bucket versioning where practical.
- Document lifecycle and retention policy before real clinical use.
- Serve previews through backend authorization or short-lived presigned URLs.
- Back up MinIO object data together with Postgres metadata.

## Authentication

Production authentication is backend-managed JWT auth. Nginx must not be the authorization boundary for `/api/v1`; it should proxy requests to the backend after handling TLS and security headers.

Development can use `BACKEND_AUTH_MODE=dev` and `POST /api/v1/auth/dev-login` with seeded personas. Production must disable dev login.

## Deployment Commands

Production (TLS) — full first-time setup + the go-live checklist live in
[production-readiness.md](production-readiness.md).

**Scripted bring-up (recommended).** After pointing DNS at the VPS (A-record, DNS-only):

1. **Install Docker** (Engine + compose plugin) — your Ansible base playbook, or any method.
2. **Prep the OS** (firewall + auto-updates + fail2ban) via either — they're twins, pick one:
   - Ansible from your control machine: `ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/prepare-server.yml` (see [deploy/ansible/](../deploy/ansible/README.md)); or
   - on the host: `sudo scripts/prepare-server.sh`
3. **Bring up the stack** on the host:

```sh
git clone git@github.com:iamsoroush/engram.git /srv/engram && cd /srv/engram
GATEWAY_API_KEY=gw_xxx scripts/bootstrap.sh        # or run without it and you'll be prompted
```

`prepare-server.sh` and `deploy/ansible/prepare-server.yml` (Ubuntu/Debian) both **assume Docker is
installed** and add the prod hardening: **ufw firewall** (SSH + 80 + 443, allowed *before* enabling so no
lockout), unattended security updates, fail2ban, an optional Docker registry mirror
(`DOCKER_REGISTRY_MIRROR` / `-e docker_registry_mirror=…` — Iran image-pull workaround), and optional SSH
lockdown (`HARDEN_SSH=1` / `-e harden_ssh=true`, applied only when an SSH key is present).

`scripts/bootstrap.sh` is idempotent and safe: it checks prerequisites, ensures swap on small boxes,
**generates `.env.prod` with fresh secrets** (only if missing — it never overwrites/rotates an existing
one), runs `scripts/deploy.sh`, **schedules nightly encrypted backups** via cron, and can **restore** a
dump (`RESTORE_FROM=/path/pg-*.sql.gz.enc scripts/bootstrap.sh`). Moving a server while keeping data =
`scp` the old `.env.prod` over first (same `BACKUP_ENCRYPTION_KEY`), then run with `RESTORE_FROM=…`.

Or step by step:

1. `cp .env.prod.example .env.prod` and fill it; generate the secrets with `scripts/gen-secrets.sh`.
2. DNS → ArvanCloud CDN; set the CDN origin to `https://$CADDY_SITE_ADDRESS` (a direct, **unproxied**
   A-record to the VPS so Caddy can obtain a Let's Encrypt cert); CDN SSL mode = full / origin-HTTPS.
3. Deploy with `scripts/deploy.sh` (build + migrate + start the TLS stack + health-check), or manually:

```sh
docker compose -f docker-compose.prod.yml -f docker-compose.prod.tls.yml --env-file .env.prod up -d --build
```

Schedule `scripts/backup.sh` via cron and rehearse `scripts/restore.sh`. Set per-service `mem_limit`/`cpus`
in `docker-compose.prod.yml` sized to your VPS (log rotation is already configured). Create an app-scoped
MinIO key (not root) for the backend and enable MinIO encryption + versioning.

Plain HTTP (dev/staging, no TLS — set `PROD_FRONTEND_PORT=80`):

```sh
docker compose -f docker-compose.prod.yml up --build -d
```

Health:

```sh
curl http://localhost/api/v1/health
```

Stop:

```sh
docker compose -f docker-compose.prod.yml down
```

If port 80 is unavailable:

```sh
PROD_FRONTEND_PORT=8080 docker compose -f docker-compose.prod.yml up --build -d
```

## ArvanCloud DNS & TLS — pick one setup

**First, delegate DNS to ArvanCloud.** At your domain **registrar** (where the domain was bought), set the
domain's **nameservers** to ArvanCloud's — the `*.ns.arvancdn.ir` hosts shown as `NS` records in your Arvan
DNS panel. That delegation is what makes the internet use Arvan for your DNS (propagation can take a few
hours). The `NS` records inside the panel are informational — leave them; the action is at the registrar.
(If you bought the domain through Arvan, it's already delegated.)

**Record types:** **A** = host → IPv4; **CNAME** = host → another host (not allowed on the bare apex `@`);
**NS** = authoritative nameservers (Arvan's — leave); **TXT** = domain/email verification; **MX** = mail.
In Arvan each record is **Proxied** (through the CDN) or **DNS-only** (resolves straight to the IP).

### Option A — Direct-to-origin (recommended for clinical/PHI)

No CDN in the request path; Caddy terminates TLS directly, so PHI is seen only by the user and your server.

| Name | Type | Value | Mode |
|---|---|---|---|
| `app` (or apex `@`) | A | `<VPS_IP>` | **DNS-only** |
| `www` | CNAME | `app.<domain>` | DNS-only |

- Set `CADDY_SITE_ADDRESS=app.<domain>` — Caddy auto-obtains a Let's Encrypt cert for it (needs 80/443
  reachable). No `origin.` record, no CDN SSL, no page rules. Caddy can also redirect `www`→`app`.
- You can still use Arvan CDN + its free SSL later for a *separate* static/marketing site.

### Option B — CDN in front (caching/DDoS; the CDN decrypts PHI — get a DPA with Arvan)

| Name | Type | Value | Mode |
|---|---|---|---|
| `app` (or apex `@`) | A | `<VPS_IP>` | **Proxied** (CDN on) |
| `origin` | A | `<VPS_IP>` | **DNS-only** (unproxied) |
| `www` | CNAME | `app.<domain>` | Proxied |

- `origin.<domain>` stays unproxied so Caddy can complete the Let's Encrypt ACME challenge and the CDN can
  reach a valid origin cert. Set `CADDY_SITE_ADDRESS=origin.<domain>`.
- In Arvan's CDN/origin settings: origin/upstream → `https://origin.<domain>`, **SSL mode = Full** (labels
  may vary; the goal is an *encrypted* CDN→origin hop validated against Caddy's cert).
- **Required page rule: bypass cache for `/api/v1/*`** (never cache PHI/API responses); also don't cache
  media; cache `/assets/*`.
- Certs: edge (browser↔CDN) = Arvan's **free SSL**; origin (CDN↔VPS) = **Caddy/Let's Encrypt**.
- Watch the **8 GB/day** free-tier cap (media-heavy) — serve large media from origin/presigned URLs.
- Path (encrypted end to end): `user → app.<domain> → Arvan CDN (TLS#1) → https://origin.<domain> → Caddy
  (TLS#2) → frontend → backend`.

## Backups & restore

`scripts/backup.sh` dumps Postgres (gzip), **encrypts it at rest** (AES-256) when `BACKUP_ENCRYPTION_KEY`
is set, optionally copies the dump **off-box** + mirrors MinIO media, and prunes old local dumps.
`scripts/restore.sh` decrypts (if `.enc`) and loads a dump back into Postgres.

> **Encrypt backups** (recommended for PHI): set `BACKUP_ENCRYPTION_KEY` in `.env.prod`
> (`scripts/gen-secrets.sh` generates one) — then a breach of the off-box bucket or provider yields
> ciphertext, not patient data. **Store that key separately from the backups** (a password manager); lose
> it and the backups are unrecoverable. *(Media off-box copies rely on MinIO/ArvanCloud S3 server-side
> encryption — enable that on the bucket.)*

**One-time off-box setup** (offsite durability — do this; a local-only backup dies with the box):

1. In the **ArvanCloud dashboard**, create an Object Storage bucket (e.g. `engram-backups`) + an access key.
2. On the VPS, install `mc` (MinIO client) and add the alias:
   ```sh
   mc alias set offsite https://<arvan-s3-endpoint> <access-key> <secret-key>
   ```
3. In `.env.prod`: `OFFSITE_ALIAS=offsite` and `OFFSITE_BUCKET=engram-backups`.

**Schedule** (cron, nightly):

```sh
0 2 * * *  cd /srv/engram && scripts/backup.sh >> /var/log/engram-backup.log 2>&1
```

**Restore** (DESTRUCTIVE — overwrites the DB; cleanest into a fresh, empty DB):

```sh
scripts/restore.sh /var/backups/engram/pg-YYYYMMDD-HHMMSS.sql.gz
```

**Rehearse restores regularly** (e.g. monthly): load the latest dump into a scratch/staging database
and verify the data + app work — an untested backup is not a backup. Note: `restore.sh` covers
**Postgres only**; recover MinIO media by re-mirroring from the off-box copy
(`mc mirror offsite/engram-backups/media local/engram-captures`).
