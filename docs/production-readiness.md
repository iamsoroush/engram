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
| **A ✅ built** | **Real auth: login / sign-up** + a **landing page** | **Done.** `POST /auth/register` onboards a clinic (tenant + founding `owner` user) and signs the founder in; email + password (phone/OTP deferred). Bilingual fa/en + RTL landing/login/sign-up (`shared/i18n` seam; authed app still English). Dev-login unchanged + still gated by `BACKEND_AUTH_MODE`. New tenants default to Basic. See [auth](backend/auth.md), [unauthenticated shell](ux/screens/login.md). |
| **A ✅ built** | **First-use onboarding / training** | **Done.** Animated guided "capture your first visit": a **spotlight** coachmark on the live capture bar with a **live first capture**, **tier-accurate** content (Basic = capture/organize, no AI claims, + a Pro upsell; Pro = AI report + memory/Q&A), "Invite your team" + "See the Pro plan" links, and **Replay guide** in the account menu. See [onboarding](ux/screens/onboarding.md). |
| **A ✅ built** | **Clinic member management + plans** | **Done.** Owner/admin **Team** screen + `clinic/team` endpoints: add members with a temp password **or attach an existing Memara account across clinics**, change role/status (owner + self protected). **Plan** screen + `PATCH /clinic/plan` to switch Basic↔Pro (no payment). See [Team](ux/screens/team.md), [Plan](ux/screens/plan.md). |
| **B** | **AI-feedback instrumentation** | Log staff **corrections** of any AI output (transcript/caption/treatment/patient-match: before→after, PII-scrubbed) + a thumbs/rating on report/brief. Doubles as the **eval golden-set harvester** (see `docs/ai_engine/eval-epic.md` §1b). |
| **B** | **Stale-client robustness** | A patient merge/delete must invalidate client caches; a 404 on a now-deleted patient should self-heal (no stuck "verify" panel). Surfaced by a real incident: deleting a merged patient left the client PATCHing a dead id → 404. |

The **A-tier (auth + landing + onboarding)** is **built** — the MVP is handable to a real user; **B-tier** is the
feedback loop that turns that user's testing into eval data + fixes a known rough edge.

An evaluator pass hardened A: per-request **live-membership authorization** (disable/role-change apply
immediately, not at token expiry), the **capture bar hidden on account screens**, **tier-honest landing**
(how-it-works/trust/placeholder-pricing; Basic led, Pro as the upgrade lane), **multi-clinic switch**
(`/auth/switch-tenant` + a switcher), sharper sign-up errors, and committed **e2e specs** (`tests/e2e/`).
Remaining A follow-ups: phone/OTP credentials, password reset, and — the top adoption risk for an
Iran-first launch — **translating the authenticated app** (the app is still English-only; the public
surfaces + onboarding are bilingual). That full-app i18n is the deferred next epic.

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
