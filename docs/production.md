# Production

## Current deployment

Engram is live at **`engram.ir`**, on a single ArvanCloud VPS (Iran region):

- **DNS:** Option A — a direct, unproxied A-record to the VPS; no CDN in the request path
  (see [DNS & TLS](#arvancloud-dns--tls--pick-one-setup)).
- **TLS:** Caddy on the box terminates HTTPS with Let's Encrypt certificates. Issuance and
  **renewal are automatic** — no cert maintenance needed.
- **AI gateway:** `gw.engram.ir` — the Europe-hosted, Iran-reachable gateway that serves all AI
  jobs (transcription, image captions, report synthesis, patient memory/matching).
- **Deploy path:** first bring-up via `scripts/bootstrap.sh`; routine deploys via
  `scripts/deploy.sh`.

This is deliberately a small single-box alpha deployment. The simplifications made for it —
and how to undo each when scaling up — are the debt register in
[production-alpha-tradeoffs.md](production-alpha-tradeoffs.md).

## Stack

Production runs the base compose plus the TLS overlay:

```sh
docker compose -f docker-compose.prod.yml -f docker-compose.prod.tls.yml --env-file .env.prod ...
```

Services:

- `caddy` (from `docker-compose.prod.tls.yml`): TLS termination; publishes host ports **80/443**
  (+ 443/udp for HTTP/3) and proxies to `frontend:80` over the internal Docker network.
- `frontend`: nginx serving the built Vite app and proxying `/api/v1` to the backend. Kept off
  the public host — `bootstrap.sh` pins `PROD_FRONTEND_PORT=127.0.0.1:8080` so Caddy owns 80/443.
- `backend`: FastAPI/uvicorn, private to the Docker network (`http://backend:8000`); runs
  `alembic upgrade head` on start.
- `ai-engine`: Celery worker executing the AI jobs against the configured gateway.
- `redis`: Celery broker/result backend.
- `postgres`: metadata store — tenants, users, patients, sessions, captures, artifacts, audit
  events, processing-job rows.
- `minio`: S3-compatible object storage for capture source files and generated artifacts; media
  is served via short-lived presigned URLs. Do not switch production back to backend-local files.
  (The `capture_data` volume is a legacy local-file mount; the storage of record is
  MinIO + Postgres.)

**Caddy is the only public entry point** — everything else stays on the internal network or a
localhost bind.

## API routing

Leave `PROD_VITE_API_URL` empty for the default same-origin setup: the browser calls
`/api/v1/...` and nginx proxies to the backend container. This avoids CORS issues and phone/LAN
problems where `localhost` would refer to the client device.

HTTPS is required for the product to function, not just for transport security: microphone
capture (`MediaRecorder`) and camera access need a secure context. (For local LAN testing over
HTTP, audio capture may fall back to file input.)

## Data safety

The product promise is that captures are not lost because the network is slow.

Safety layers:

- Browser IndexedDB pending outbox before upload, with retry for failed uploads.
- Browser warning while unsynced captures exist.
- A capture is safely transferred only after the source object exists in MinIO **and** its
  metadata is committed in Postgres; if either side fails, the API does not return a successful
  upload. The browser outbox remains the safety copy until backend success.
- Synced browser cache is only a convenience for fast preview and may be evicted; unsynced
  outbox data must never be silently deleted.

## Environment variables

**[`.env.prod.example`](../.env.prod.example) is the authoritative variable list** — copy it to
`.env.prod` and generate the secrets with `scripts/gen-secrets.sh` (`bootstrap.sh` does both when
`.env.prod` is missing). The groups it covers:

- **Domain/TLS:** `CADDY_SITE_ADDRESS`, `PROD_FRONTEND_PORT` (keep `127.0.0.1:8080` under Caddy).
- **Core secrets:** `POSTGRES_*`, `MINIO_ROOT_*`, `BACKEND_JWT_SECRET`, `AI_ENGINE_INTERNAL_TOKEN`.
- **Auth:** `BACKEND_AUTH_MODE=production` — mandatory; disables dev-login.
- **Object storage:** `BACKEND_OBJECT_STORAGE_*`, including `..._PUBLIC_ENDPOINT` (public base for
  presigned URLs).
- **AI:** `AI_ENGINE_TRANSCRIPTION_BASE_URL/_API_KEY/_MODEL` (the gateway),
  `BACKEND_REPORT_SYNTHESIS_ENABLED` + `AI_ENGINE_REPORT_SYNTHESIS_MODEL/_REASONING_EFFORT`, and
  optional `AI_ENGINE_CAPTION_MODEL` / `AI_ENGINE_PATIENT_MEMORY_MODEL` (blank = fall back to the
  transcription model).
- **Backups:** `BACKUP_DIR/_RETAIN_DAYS/_ENCRYPTION_KEY`, `OFFSITE_ALIAS`, `OFFSITE_BUCKET`.
- **Monitoring overlay:** `GRAFANA_*` / `GLITCHTIP_*` / Sentry DSNs — see
  [monitoring.md](monitoring.md).

## Operational posture

In place and live:

- TLS end-to-end with auto-renewed certs (Caddy).
- Backend-managed JWT auth; dev-login disabled (`BACKEND_AUTH_MODE=production`); per-request
  live-membership authorization; tenant/clinic isolation.
- Nightly **encrypted** Postgres backups on cron (installed by `bootstrap.sh`) +
  `scripts/restore.sh`; rehearse restores regularly.
- nginx upload size limit, security headers, gzip; container log rotation.
- OS hardening via server prep: ufw firewall (SSH/80/443 only), unattended security updates,
  fail2ban.
- Audit events recorded in Postgres.

Open hardening items (each with its scale-up action in
[production-alpha-tradeoffs.md](production-alpha-tradeoffs.md)):

- No per-service resource limits (`mem_limit`/`cpus`) in the prod compose.
- The backend uses the **MinIO root key** — an app-scoped key (+ server-side encryption + bucket
  versioning) is still pending.
- Backups are **local-only unless `OFFSITE_ALIAS` is set** — they die with the box otherwise.
- The monitoring overlay is built but **not deployed** — see [monitoring.md](monitoring.md).

## MinIO security (target posture)

- Keep MinIO API and console on a private network; no public bucket access.
- Separate backend app credentials from operational admin credentials; limit backend credentials
  to the required bucket. *(Current deviation: backend uses the root key — see above.)*
- Enable server-side encryption and bucket versioning where practical.
- Serve previews through backend authorization or short-lived presigned URLs (as built).
- Back up MinIO object data together with Postgres metadata.

## Authentication

Production authentication is backend-managed JWT auth (see [backend/auth.md](backend/auth.md)).
Caddy/nginx are not the authorization boundary for `/api/v1` — they proxy to the backend after
TLS and headers. Development can use `BACKEND_AUTH_MODE=dev` + `POST /api/v1/auth/dev-login`
with seeded personas; production disables dev-login.

## Deployment

### First-time server setup

1. **Point DNS at the VPS** (A-record, DNS-only — Option A below).
2. **Prep the box** from your control machine with
   **`deploy/ansible/setup-production.yml`** — the one you want for a bare Ubuntu box: ArvanCloud
   apt + Docker registry mirrors (Iran-aware, no GitHub needed), Docker, ufw, swap. See
   [deploy/ansible/](../deploy/ansible/README.md). (`prepare-server.yml` /
   `scripts/prepare-server.sh` are older variants that assume Docker is already installed and add
   only the hardening: firewall, unattended-upgrades, fail2ban, optional SSH lockdown.)
3. **Bring up the stack** on the host:

```sh
git clone git@github.com:iamsoroush/engram.git /srv/engram && cd /srv/engram
GATEWAY_API_KEY=gw_xxx scripts/bootstrap.sh        # or run without it and you'll be prompted
```

`scripts/bootstrap.sh` is idempotent and safe: it checks prerequisites, ensures swap on small
boxes, **generates `.env.prod` with fresh secrets** (only if missing — it never
overwrites/rotates an existing one), runs `scripts/deploy.sh`, **schedules nightly encrypted
backups** via cron, and can **restore** a dump
(`RESTORE_FROM=/path/pg-*.sql.gz.enc scripts/bootstrap.sh`). Moving a server while keeping data =
`scp` the old `.env.prod` over first (same `BACKUP_ENCRYPTION_KEY`), then run with
`RESTORE_FROM=…`.

### Routine deploys

```sh
scripts/deploy.sh
```

`deploy.sh` = `git pull --ff-only` → build → `up -d` with both compose files (migrations run on
backend start) → wait for backend health, failing loudly if it doesn't come up.

**Host can't reach GitHub** (common from Iran): deliver the code by rsync, then

```sh
SKIP_GIT_PULL=1 scripts/deploy.sh
```

— the working tree is used as-is, no pull attempted.

**Rollback:** `git checkout <previous-good-sha> && scripts/deploy.sh` (with `SKIP_GIT_PULL=1` on
rsync-fed hosts). The DB schema migrates **forward** on deploy — rolling code back past a
migration needs a matching DB restore (`scripts/restore.sh`).

Manual equivalent of a deploy:

```sh
docker compose -f docker-compose.prod.yml -f docker-compose.prod.tls.yml --env-file .env.prod up -d --build
```

Plain HTTP (dev/staging only, no TLS — set `PROD_FRONTEND_PORT=80`):

```sh
docker compose -f docker-compose.prod.yml up --build -d
```

Health check: `curl https://engram.ir/api/v1/health` (externally) or
`curl http://localhost:8080/api/v1/health` on the box.

### CI

`.github/workflows/ci.yml` runs on every PR and on pushes to `main`: backend + ai-engine test
suites, frontend typecheck + unit tests + i18n guard, hermetic Playwright e2e (mocked API),
prod-compose validation, and — merge-blocking — the **`e2e-stack`** job, which boots the real compose
stack gateway-less (`docker-compose.e2e.yml`) and runs the P0 real-stack Playwright suite against it
(API contract, migrations, MinIO, Celery pipeline, tier gating, public token pages). A second job,
**`e2e-stack-ai`** (push-to-`main` only), adds a deterministic mock LLM gateway
(`docker-compose.e2e-ai.yml`) and runs the P1 synthesis suite. Both are keyless. See
[the frontend README's Testing section](../apps/frontend/README.md). `.github/workflows/eval.yml` is
the **manual-only, non-blocking** AI golden-set eval (run from the Actions tab). Deploys are not
CI-gated — the box builds whatever is checked out (tracked in
[production-alpha-tradeoffs.md](production-alpha-tradeoffs.md)).

## ArvanCloud DNS & TLS — pick one setup

> **Current production uses Option A** at `engram.ir`.

**First, delegate DNS to ArvanCloud.** At your domain **registrar** (where the domain was bought), set the
domain's **nameservers** to ArvanCloud's — the `*.ns.arvancdn.ir` hosts shown as `NS` records in your Arvan
DNS panel. That delegation is what makes the internet use Arvan for your DNS (propagation can take a few
hours). The `NS` records inside the panel are informational — leave them; the action is at the registrar.
(If you bought the domain through Arvan, it's already delegated.)

**Record types:** **A** = host → IPv4; **CNAME** = host → another host (not allowed on the bare apex `@`);
**NS** = authoritative nameservers (Arvan's — leave); **TXT** = domain/email verification; **MX** = mail.
In Arvan each record is **Proxied** (through the CDN) or **DNS-only** (resolves straight to the IP).

### Option A — Direct-to-origin (recommended for clinical/PHI; in use)

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

**Schedule** — `bootstrap.sh` installs the nightly cron automatically; the manual equivalent:

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
