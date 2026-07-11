# Production Alpha Trade-offs → Scale-up

This deployment is intentionally simplified for **alpha testing** — 1–2 users on a single small
ArvanCloud VPS, no monitoring. Each choice below is safe for alpha but should be revisited before a real
clinic or larger load. Treat this as the **migration checklist**: when you move to a bigger server / real
users, walk the table and the fast-path at the bottom.

Companion to [production.md](production.md) (current shape + deploy runbook) and
[monitoring.md](monitoring.md) (the built-but-undeployed observability overlay).

## Trade-offs we made (and how to undo them)

| Area | Alpha choice (why) | Trade-off / risk | Scale-up action |
|---|---|---|---|
| **Topology** | Everything on one VPS (postgres, minio, redis, backend, ai-engine, frontend, caddy) | No isolation; one box = single point of failure; resource contention under load | Split data services + the ai-engine worker to their own nodes (architecture already separates them) |
| **Server size** | 2 vCPU / 2–4 GB + swap | Frontend build leans on swap (slow, OOM-prone); no headroom | 8 GB+; build images in CI/registry instead of on the box |
| **Image build** | `deploy.sh` builds on the box | Slow deploys; RAM spike is the main reason swap is needed | Build in CI → push to a registry → `pull` on the server |
| **Monitoring** | Overlay **built but not deployed** (`deploy.sh` doesn't include it) | Blind to errors, queue depth, disk, cert expiry, backup freshness | Enable `docker-compose.monitoring.yml` (Prometheus/Grafana/GlitchTip/Uptime Kuma; ~2–3 GB) + alerts — see [monitoring.md](monitoring.md) |
| **Object storage** | Self-hosted MinIO, single node, local volume; backend uses the **MinIO root** key | App holds full storage admin; no replication; root-key leak = total media compromise | App-scoped key + server-side encryption + bucket versioning; or migrate to **ArvanCloud S3** (managed durability) — backend is S3-compatible, just swap endpoint+creds |
| **Mixed audio format store** | Canonical audio moved to MP3 16 kHz mono (transcode-on-ingest) with **no bulk migration** — pre-existing captures stay WAV | The object store holds both WAV (old, ~8× larger) and MP3 (new); readers key off the stored `artifact.mime_type` so both play/transcribe fine | Optional one-off backfill: transcode legacy WAV artifacts → canonical MP3 and rewrite their artifact mime/size (reclaims the old WAV bytes). Not required for correctness |
| **Backups** | Nightly encrypted pg dump, **local-only** (offsite off unless `OFFSITE_ALIAS` set) | Backups die with the box; media not mirrored | Set `OFFSITE_ALIAS` + `mc` → ArvanCloud S3; rehearse `restore.sh` monthly; mirror media |
| **Secrets** | `.env.prod` on the box, `scp` to move servers | Server is the only copy; no versioning/rotation/audit; losing `BACKUP_ENCRYPTION_KEY` = unrecoverable backups | Source-of-truth in a password manager (min) → **Ansible Vault**-templated `.env.prod` (fits our setup) → self-hosted Infisical/Vault at scale |
| **Auth tokens** | Refresh token in browser `localStorage` (needed so refresh-survives-reload works in prod) | XSS could exfiltrate the refresh token | Move the refresh token to a Secure **HTTP-only cookie** (backend-set); keep access token in memory |
| **TLS edge** | Option A direct-to-origin (Caddy on the box), no CDN | No caching/DDoS/WAF; single origin | Option B (ArvanCloud CDN in front, with a DPA for PHI) or a WAF; keep Caddy as origin TLS |
| **CI / deploy gating** | CI runs on PRs + `main` (backend/ai-engine tests, typecheck, unit/i18n, hermetic e2e, compose validation — since 2026-06-15), but images build **on the box** and `deploy.sh` doesn't check CI | A broken commit can still be deployed if you skip checking CI | Build in CI → push to a registry → `pull` on the server; gate `deploy.sh` on a green `main` |
| **Environments** | Deploy straight to prod | No safe place to test deploys | Add a staging stack (own DB/bucket) |
| **Resource limits** | No `mem_limit`/`cpus` set in prod compose | A runaway container can starve the box | Set per-service limits sized to the VPS (log rotation is already configured) |
| **Synthesis model** | `gpt-5.4-nano` (cheaper) | Eval golden set was validated on `gpt-5.4-mini`, not nano | Run `apps/ai_engine/eval/run_all.py` on nano; move to a validated/larger model if it regresses |
| **AI gateway** | Single EU instance | No redundancy; gateway down = no transcription/synthesis | HA gateway / failover; monitor reachability from the VPS |
| **ai-engine worker** | Single worker, default concurrency | Limited throughput under burst | Scale worker concurrency / move to its own node |
| **Postgres / Redis** | Default config, no pooling | Fine for low load; not tuned | Tuned configs + connection pooling; consider managed Postgres |
| **Postgres image (pgvector)** | `pgvector/pgvector:pg16` (Debian) replaces `postgres:16-alpine` — the Q&A knowledge retrieval needs the `vector` extension in the **existing** Postgres (no separate vector DB) | The **first deploy against the existing prod data volume changes the libc collation provider** (alpine musl → Debian glibc): text btree indexes must be rebuilt or sort/uniqueness can drift | **One-time, in the maintenance window:** after the image swap `docker compose up -d postgres`, run `REINDEX DATABASE engram;` (Postgres logs a collation-version-mismatch warning until you do), then `ALTER DATABASE engram REFRESH COLLATION VERSION;`. A fresh volume needs neither. |
| **Q&A embeddings gateway** | `BACKEND_EMBEDDINGS_*` **unset** in prod ⇒ Q&A retrieval is lexical-only (deterministic) | No semantic recall for paraphrased questions until an embeddings endpoint is configured; the embedding cost, once on, is **not metered** through the worker usage sink | Set `BACKEND_EMBEDDINGS_BASE_URL/_API_KEY/_MODEL` to the gateway; add its spend to the AI-usage accounting when it becomes non-trivial |

## Fast migration path (bigger server / real users)

When the time comes, roughly in this order:

1. **Provision** a larger VPS (8 GB+); prep it (`deploy/ansible/setup-production.yml`), set a Docker registry mirror if needed.
2. **Secrets** into Ansible Vault (or a password manager) as the source of truth; stop relying on `scp`.
3. **Object storage:** switch to ArvanCloud S3 *or* give MinIO an app-scoped key + encryption + versioning.
4. **Backups:** turn on off-box (`OFFSITE_ALIAS` → ArvanCloud S3) and rehearse a restore.
5. **Monitoring + alerts:** bring up the monitoring overlay; wire alerts (errors, queue depth, disk, cert, backup freshness).
6. **Deploy gating:** build images in CI → registry → `pull` on the server; make deploys require a green `main` (CI itself already runs on PRs + `main`).
7. **Staging** environment for deploy rehearsals.
8. **Synthesis model:** re-run evals; pick the model that meets quality at acceptable cost.
9. **Edge:** decide CDN/WAF (Option B + DPA) vs staying direct-to-origin.
10. **Resource limits** + Postgres tuning sized to the new box.

Nothing here blocks alpha — it's the deliberate debt list, kept so the jump to "real" is a checklist, not an archaeology project.
