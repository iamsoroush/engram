# Monitoring (self-hosted)

Self-hosted observability for the production stack, delivered as a Compose **overlay**
(`docker-compose.monitoring.yml`). Everything runs **on the box** — no foreign SaaS
(Sentry.io, Datadog, etc.), which may be blocked/sanctioned from the **ArvanCloud / Iran**
deployment. Companion to [production.md](production.md).

> **Status: built, not deployed.** The overlay, dashboards, and alert rules are committed and
> validated, but production does not run them — `scripts/deploy.sh` starts only the app + TLS
> compose files, a deliberate alpha trade-off
> ([production-alpha-tradeoffs.md](production-alpha-tradeoffs.md)). See
> [Current status + how to enable](#current-status--how-to-enable).

## What's monitored

The production watch-list: API error rate + p95 latency · **failed uploads** (product-critical) ·
**AI-job failure rate + Celery/Redis queue depth** · Postgres connections + disk · object-store
disk/usage · Redis memory · container restarts · host CPU/mem/disk · **TLS cert expiry** ·
**backup freshness**. How each is covered:

| Concern | Source | Surfaced in |
|---|---|---|
| Host CPU / mem / disk / load | node-exporter | Grafana, alerts |
| Per-container CPU/mem, **container restarts**, up/down | cAdvisor | Grafana, alerts |
| **Postgres** connections vs max, DB size, locks, up | postgres-exporter | Grafana, alerts |
| **Redis memory**, clients, keyspace | redis-exporter | Grafana, alerts |
| **Celery / Redis queue depth** (`ai_jobs`) | redis-exporter `--check-keys` | Grafana, alerts |
| **Object-store / Postgres / backup disk** | node-exporter (host filesystem) | Grafana, alerts |
| Uptime of `/api/v1/health` (https + http) | Uptime Kuma | Uptime Kuma, alerts |
| **TLS cert expiry** | Uptime Kuma | Uptime Kuma, alerts |
| **API error rate + p95 latency** | backend `/metrics` (wired — see [Application metrics](#application-metrics-metrics--as-built)) | Grafana, alerts |
| **Failed uploads** (product-critical) | backend `/metrics` counter `engram_capture_uploads_failed_total` (wired) | Grafana, alerts |
| **AI-job failure rate** | backend `/metrics` counter `engram_ai_jobs_total{status=…}` (wired) | Grafana, alerts |
| **Application errors / stack traces** | GlitchTip (Sentry-compatible) *(SDKs installed; DSNs minted after first GlitchTip login)* | GlitchTip UI |
| **Backup freshness** | see [Backup freshness](#backup-freshness) *(metric not yet emitted)* | alert (manual hook) |

The app-side wiring (backend `/metrics`, the two product counters, DSN-gated Sentry SDKs in
backend + frontend) is **done** — everything above lights up as soon as the overlay itself is
deployed, except the GlitchTip DSNs (set after its first login) and the backup-freshness metric.

## Why this stack

- **Prometheus + Grafana + exporters** over Netdata: exporters cover Postgres, Redis,
  **Celery queue depth**, and containers with one consistent query language + alert rules;
  Grafana provisioning gives a reproducible dashboard checked into the repo. Netdata is great
  for a quick single-box view but is weaker for app-level/queue metrics and rule-based alerts.
- **Uptime Kuma** for black-box uptime + TLS cert-expiry — purpose-built, trivial to run.
- **GlitchTip** for error tracking: **Sentry-API-compatible**, so the existing `sentry-sdk`
  ecosystem works against a self-hosted DSN — no Sentry.io dependency.

## Services & ports

All UIs bind to **`127.0.0.1` only** — nothing is published to the public internet.

| Service | Image | Internal port | Host bind | Purpose |
|---|---|---|---|---|
| prometheus | `prom/prometheus:v2.53.1` | 9090 | `127.0.0.1:9090` | metrics store + alerts |
| grafana | `grafana/grafana:11.1.4` | 3000 | `127.0.0.1:3000` | dashboards |
| node-exporter | `prom/node-exporter:v1.8.2` | 9100 | internal | host metrics |
| cadvisor | `gcr.io/cadvisor/cadvisor:v0.49.1` | 8080 | internal | container metrics |
| postgres-exporter | `quay.io/prometheuscommunity/postgres-exporter:v0.15.0` | 9187 | internal | Postgres metrics |
| redis-exporter | `oliver006/redis_exporter:v1.62.0-alpine` | 9121 | internal | Redis + queue depth |
| uptime-kuma | `louislam/uptime-kuma:1.23.16` | 3001 | `127.0.0.1:3001` | uptime + cert expiry |
| glitchtip-web | `glitchtip/glitchtip:v4.2.4` | 8000 | `127.0.0.1:8080` | error-tracking UI/API |
| glitchtip-worker | `glitchtip/glitchtip:v4.2.4` | — | internal | error-tracking worker |
| glitchtip-migrate | `glitchtip/glitchtip:v4.2.4` | — | (one-shot) | GlitchTip DB migrate |
| glitchtip-postgres | `postgres:16-alpine` | 5432 | internal | GlitchTip's own DB |
| glitchtip-redis | `redis:7-alpine` | 6379 | internal | GlitchTip's own broker |

**Networking.** The overlay runs in the **same Compose project** as the prod stack, so its
services share the prod **`default`** network and reach `backend`, `postgres`, `redis` by name
— no app-stack edits needed. GlitchTip's own Postgres/Redis sit on an isolated
`monitoring_internal` network (kept off the app DB). GlitchTip web also joins `default` so the
app containers could reach it directly if you ever prefer an internal DSN.

> **Image verification.** `glitchtip/glitchtip:v4.2.4`, `prom/node-exporter:v1.8.2`, and
> `gcr.io/cadvisor/cadvisor:v0.49.1` were not pulled in this environment — confirm the exact
> tags resolve (or bump to the current stable) on first deploy. All other tags are
> well-established. Pin tags (never `latest`) so deploys are reproducible.

## Start / stop

```sh
# start prod + monitoring together (same project => shared network)
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml up -d

# view monitoring logs
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml logs -f prometheus grafana

# stop just monitoring (leave the app running)
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml \
  stop prometheus grafana node-exporter cadvisor postgres-exporter redis-exporter \
       uptime-kuma glitchtip-web glitchtip-worker glitchtip-postgres glitchtip-redis

# full teardown
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml down
```

After Prometheus is up, reload rules without a restart:
`curl -X POST http://localhost:9090/-/reload` (from a tunnel — see below).

## Accessing the UIs safely

The UIs are bound to `127.0.0.1` on the server, so they are **not reachable from the internet**.
Two safe options:

### Option A — SSH tunnel (recommended for ops)

```sh
ssh -N \
  -L 9090:127.0.0.1:9090 \  # Prometheus
  -L 3000:127.0.0.1:3000 \  # Grafana
  -L 3001:127.0.0.1:3001 \  # Uptime Kuma
  -L 8080:127.0.0.1:8080 \  # GlitchTip
  user@<server>
```

Then open `http://localhost:3000` (Grafana), `:9090`, `:3001`, `:8080` on your laptop.

### Option B — behind the CDN with auth

Expose a UI at e.g. `https://grafana.<domain>` **only** behind an extra auth layer (nginx/Caddy
Basic Auth or an auth proxy) upstreaming to the same localhost ports. GlitchTip and Grafana have
their own logins, but do **not** publish them without that extra layer + TLS. Never expose
Prometheus or the raw exporters publicly (they have no auth).

## Environment variables

All of these are already stubbed in `.env.prod.example`, and `scripts/gen-secrets.sh` generates
the secret ones — fill them in `.env.prod` before starting the overlay.

### Required (have no safe default; `config` fails without them)

| Var | Used by | Notes |
|---|---|---|
| `GRAFANA_ADMIN_PASSWORD` | grafana | Grafana admin login. **Required.** |
| `GLITCHTIP_SECRET_KEY` | glitchtip-* | Django secret. Generate: `openssl rand -hex 32`. **Required.** |
| `GLITCHTIP_POSTGRES_PASSWORD` | glitchtip-postgres + glitchtip-* | GlitchTip DB password. **Required.** |

`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` are **already** in `.env.prod` (reused by
postgres-exporter — no new vars).

### Optional (sane defaults shown)

| Var | Default | Purpose |
|---|---|---|
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ROOT_URL` | `http://localhost:3000` | set to `https://grafana.<domain>` if CDN-fronted |
| `PROMETHEUS_RETENTION` | `30d` | Prometheus TSDB retention |
| `GLITCHTIP_DOMAIN` | `http://localhost:8080` | GlitchTip's external URL (scheme required) |
| `GLITCHTIP_DEFAULT_FROM_EMAIL` | `glitchtip@localhost` | sender for invite/alert mail |
| `GLITCHTIP_EMAIL_URL` | `consolemail://` | SMTP, e.g. `smtp://user:pass@host:587` |
| `GLITCHTIP_MAX_EVENT_LIFE_DAYS` | `90` | auto-drop old events (bounds disk) |
| `GLITCHTIP_CELERY_AUTOSCALE` | `1,3` | GlitchTip worker concurrency |

### Error-tracking DSN (set after first GlitchTip login)

GlitchTip mints a DSN per project in its UI. Add the resulting DSN as the var the app reads.
The backend/frontend wiring (out of this effort's scope) should read **exactly** these names:

| Var | Read by | Value |
|---|---|---|
| `BACKEND_SENTRY_DSN` | backend (FastAPI) | GlitchTip project DSN for the API |
| `VITE_SENTRY_DSN` | frontend build (Vite) | GlitchTip project DSN for the SPA |
| `SENTRY_ENVIRONMENT` | backend + frontend | e.g. `production` |
| `SENTRY_TRACES_SAMPLE_RATE` | backend (optional) | e.g. `0.1` (perf tracing) |

> GlitchTip is Sentry-API-compatible, so the standard `sentry-sdk` (Python) and
> `@sentry/react` (JS) point at the GlitchTip DSN unchanged. Reachability: the backend can use
> the **internal** DSN host `glitchtip-web:8000` (both on `default` net) to avoid leaving the
> box; the browser must use the **public** GlitchTip URL (`GLITCHTIP_DOMAIN`).

## Application metrics (`/metrics`) — as built

The backend **exposes `/metrics`** via `prometheus-fastapi-instrumentator`
(`apps/backend/app/observability/`) — mounted outside `/api/v1`, unauthenticated but reachable
only on the internal Docker network, matching Prometheus's `backend` scrape job
(`backend:8000/metrics`):

- Default HTTP metrics (`http_requests_total{status=...}`,
  `http_request_duration_seconds_bucket`) feed the dashboard + `APIHighErrorRate` /
  `APIHighLatency` alerts.
- Two custom product-critical counters (names referenced by
  `monitoring/prometheus/alert.rules.yml`): `engram_capture_uploads_failed_total`
  (incremented on the capture-upload error path) and `engram_ai_jobs_total{status=…}`
  (incremented on AI-job terminal states).

Queue depth (`redis_key_size{key="ai_jobs"}`) additionally proxies AI-job health straight from
the redis-exporter, independent of the backend.

## Dashboards & datasource

Grafana auto-provisions on boot from `monitoring/grafana/provisioning/`:

- **Datasource** — Prometheus at `http://prometheus:9090` (default).
- **Dashboard** — *Engram — Production Overview* (`monitoring/grafana/dashboards/engram-overview.json`):
  host CPU/mem/disk, per-container CPU/mem, Postgres connections + DB size, Redis memory,
  Celery `ai_jobs` queue depth, and API request-rate + p95 panels (fed by the backend's `/metrics`).

For richer per-component views, import community dashboards by ID in Grafana: Node Exporter Full
(**1860**), cAdvisor (**14282**), Postgres (**9628**), Redis (**763**).

## Alerts

Rules live in `monitoring/prometheus/alert.rules.yml` (mounted into Prometheus). Highlights:
host CPU/mem/disk (warn + critical), container restart loops, scrape-target down, Postgres
down / connections >80% of max, Redis down / memory >85% / **`ai_jobs` backlog >100**, health
endpoint down, **TLS cert expiring <14d**, API 5xx >5%, p95 >1.5s, failed uploads, AI-job
failure >20%.

Prometheus only **evaluates** rules; to be **notified** you need a router. Two options:

- **Grafana alerting (simplest)** — Grafana ships with an alerting engine + contact points
  (email/Telegram/webhook). Recreate the key conditions as Grafana alert rules and add a
  contact point. No extra container.
- **Alertmanager** — add a `prom/alertmanager` service and point `alerting.alertmanagers` in
  `monitoring/prometheus/prometheus.yml` at it (currently empty so Prometheus starts cleanly).

**Telegram** is a good fit for the Iran deployment (works without US SaaS); both Grafana and
Alertmanager support Telegram webhooks.

### Uptime Kuma (uptime + cert expiry)

After first login at `http://localhost:3001` (via tunnel):

1. Create an **admin** account (Uptime Kuma has no default creds; first visitor sets them).
2. Add a monitor: type **HTTP(s)**, URL `https://<domain>/api/v1/health`, interval 60s.
   Enable **certificate expiry** notification (e.g. 14 days). This covers the **TLS cert
   expiry** + **uptime** items directly in Uptime Kuma even before Grafana alerting exists.
3. Add a second monitor for the http→https redirect or the origin if useful.
4. **AI gateway** monitor: type **HTTP(s)** (or **TCP** if it exposes no health URL), target the EU
   transcription gateway (`AI_ENGINE_TRANSCRIPTION_BASE_URL`, i.e. `gw.engram.ir`), interval 60s. AI
   jobs depend on it, so this alerts you when the gateway becomes unreachable from the server — even
   though it's not part of our own stack. (Metric-based alternative: alert on the
   `engram_ai_jobs_total{status="failed"}` counter.)
5. Configure a notification channel (Telegram/email) in Settings → Notifications.

To also surface Uptime Kuma in Grafana, enable its Prometheus metrics (Settings → API Keys),
which feeds the `uptime-kuma` scrape job and the `HealthEndpointDown` / `TLSCertExpiringSoon`
rules.

### Backup freshness

Nightly encrypted backups are live (`scripts/backup.sh` on cron), but they don't yet emit a
freshness signal Prometheus can alert on. Recommended wiring (still open):

- Have `scripts/backup.sh` write a metric to the **node-exporter textfile collector** on
  success, e.g. `engram_last_backup_success_timestamp_seconds <epoch>`, then add an alert:
  `time() - engram_last_backup_success_timestamp_seconds > 90000` (>25h). This needs
  node-exporter's `--collector.textfile.directory` + a mounted dir. Until then, monitor backup
  freshness via Uptime Kuma push or a cron heartbeat check.

## Current status + how to enable

Already in place: the overlay + config under `monitoring/`, the env vars stubbed in
`.env.prod.example` (secrets generated by `scripts/gen-secrets.sh`), the backend `/metrics`
endpoint + product counters, and DSN-gated Sentry SDKs in backend and frontend. **Not running in
production** — `scripts/deploy.sh` doesn't include the overlay.

To enable on the prod box:

1. Fill the monitoring secrets in `.env.prod` (`GRAFANA_ADMIN_PASSWORD`, `GLITCHTIP_SECRET_KEY`,
   `GLITCHTIP_POSTGRES_PASSWORD` — see [Environment variables](#environment-variables)).
2. Add `-f docker-compose.monitoring.yml` to the prod `docker compose` invocation — the natural
   place is the `FILES` list in `scripts/deploy.sh` — then deploy.
3. First-login setup: Grafana admin, [Uptime Kuma monitors](#uptime-kuma-uptime--cert-expiry),
   a GlitchTip project → put its DSNs (`BACKEND_SENTRY_DSN`, `VITE_SENTRY_DSN`) in `.env.prod`
   and redeploy backend + frontend.

Still open beyond that:

- **Backup-freshness metric** — emit the textfile metric from `scripts/backup.sh`
  (see [Backup freshness](#backup-freshness)).
- **(Optional) CDN/nginx-fronted UIs** — an auth-protected vhost upstreaming to the localhost
  ports; otherwise access stays SSH-tunnel-only.

## Validation

```sh
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml config -q
```

passes with dummy values for the required secrets. See the overlay header for the exact run
command.
