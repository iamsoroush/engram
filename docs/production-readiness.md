# Production Readiness

> The gap list + go-live checklist to take Notari/Memara from "runs in prod compose" to "safe for real
> clinical data". Companion to [production.md](production.md) (current prod shape + ops concerns) and
> [architecture.md](architecture.md). **First deployment target:** ArvanCloud (Iran region); AI gateway in
> Europe, reachable from Iran.

## Current state — solid foundation (not starting from zero)

`docker-compose.prod.yml` already provides: per-service **healthchecks**, `restart: unless-stopped`,
**persistent volumes** (postgres/minio/redis/captures), **required-secret enforcement** (`:?required`),
`alembic upgrade head` on boot, proxy-aware uvicorn (`--proxy-headers --forwarded-allow-ips '*'`), an
nginx **SPA + `/api/v1` proxy**, presigned-URL media, and **dev-login disabled** in prod
(`BACKEND_AUTH_MODE=production`). The work below closes the remaining gaps.

## Decisions for this deployment (ArvanCloud / Iran-first, global later)

- **Host + edge:** ArvanCloud VPS + **ArvanCloud CDN** as the TLS edge (cert, caching, DDoS/WAF —
  region-native, no sanctions issue). Add **Caddy** (Let's Encrypt) or an Arvan origin cert on the box so
  the CDN→origin hop is also HTTPS (no plaintext PHI, even internally).
- **Object storage:** MinIO works today; **prefer ArvanCloud S3-compatible object storage** (backend is
  already S3-compatible — endpoint+creds swap) for managed durability + offsite-by-default.
- **AI gateway:** Europe, reachable from Iran → the configured-gateway design works unchanged.
- **Monitoring:** **self-hosted** (US SaaS like Sentry.io may be blocked from Iran) — Uptime Kuma +
  Netdata or Prometheus/Grafana + **GlitchTip** (Sentry-compatible) on the box.
- **Topology:** one repo, one server. Split the ai-engine worker / data services to their own nodes only
  when scale demands (architecture already separates them).

## Gaps & tasks

### P0 — before any real clinical data
| # | Task | Lands in repo |
|---|---|---|
| T1 | **TLS edge** — ArvanCloud CDN config (runbook) + **Caddy origin TLS** service | Caddyfile + prod-compose overlay + docs |
| T2 | **Prod secrets** — `.env.prod.example` + generator; real `.env` never committed | env template, `scripts/gen-secrets.sh` |
| T3 | **Backups + tested restore** — `pg_dump` + object-store mirror to **off-box** (Arvan S3), scheduled | `scripts/backup.sh`, `restore.sh`, cron + runbook |
| T4 | **Harden** — compose resource limits + log rotation; nginx `client_max_body_size` (uploads!) + security headers + gzip; MinIO/Arvan-S3 **app-scoped creds** + encryption + versioning | compose + `nginx.conf` edits |
| — | **OS/firewall** (server, not repo) — only 80/443 + SSH; harden SSH; unattended security updates | runbook |

### P1 — at / just after launch
| # | Task | Lands in repo |
|---|---|---|
| T5 | **Deploy script + runbook** — pull → build → migrate → up → health-verify + rollback | `scripts/deploy.sh`, this doc / production.md |
| T6 | **Monitoring + alerting** — Uptime Kuma + Netdata/Prometheus-Grafana + GlitchTip; alerts | `docker-compose.monitoring.yml` + wiring |
| T7 | **CI** — 200 backend + 52 ai_engine tests + `tsc` on every PR | `.github/workflows/ci.yml` |

### P2 — as you grow
Log aggregation (Loki) · static/media CDN tuning · managed Postgres · staging environment · horizontal
scale of the ai-engine worker.

### Product launch gaps (user-facing — block a real-user MVP, not just infra)
The infra tasks above make prod *safe*; these make it *usable by a real user who isn't us*.

| Pri | Item | Notes |
|---|---|---|
| **A** | **Real auth: login / sign-up** (today only dev-login personas; `BACKEND_AUTH_MODE=production` disables them) + a **landing page** | Sign-up = a clinic onboards (tenant + first user); login for existing users. Backend already has JWT auth + roles/tenants (`docs/backend/auth.md`) — extend with real credentials. Iran-first (phone vs email?), bilingual (app language). |
| **A** | **First-use onboarding / training** | Capture-first is unfamiliar — a guided first capture or short coachmark tour so a new clinician isn't lost. |
| **B** | **AI-feedback instrumentation** | Log staff **corrections** of any AI output (transcript/caption/treatment/patient-match: before→after, PII-scrubbed) + a thumbs/rating on report/brief. Doubles as the **eval golden-set harvester** (see `docs/ai_engine/eval-epic.md` §1b). |
| **B** | **Stale-client robustness** | A patient merge/delete must invalidate client caches; a 404 on a now-deleted patient should self-heal (no stuck "verify" panel). Surfaced by a real incident: deleting a merged patient left the client PATCHing a dead id → 404. |

The **A-tier (auth + landing + onboarding)** is the gate to handing the MVP to a real user; **B-tier** is the
feedback loop that turns that user's testing into eval data + fixes a known rough edge.

## What to monitor (T6 detail)
API error rate + p95 latency · **failed uploads** (product-critical) · **AI-job failure rate + Celery/Redis
queue depth** · Postgres connections + disk · object-store disk/usage · Redis memory · container restarts ·
host CPU/mem/disk · **TLS cert expiry** · **backup freshness**.

## Go-live checklist
- [ ] HTTPS end-to-end (CDN edge **and** origin)
- [ ] Strong secrets generated; real `.env` not committed; `BACKEND_AUTH_MODE=production` (dev-login off)
- [ ] Backups scheduled **and a restore rehearsed**
- [ ] Object store: app-scoped creds, encryption, versioning, private
- [ ] Container resource limits + log rotation
- [ ] nginx: upload size limit, security headers, gzip
- [ ] Firewall (80/443 + SSH only), SSH hardened, auto security updates
- [ ] Monitoring + alerts live (uptime, errors, metrics, backup freshness)
- [ ] Deploy runbook + rollback documented
- [ ] CI green on `main`
- [ ] DNS → ArvanCloud CDN → origin; cert valid; `curl https://<domain>/api/v1/health` OK
- [ ] `docs/qa/aes-basic-smoke.md` passes against production
