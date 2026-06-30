# Production Alpha Trade-offs → Scale-up

This deployment is intentionally simplified for **alpha testing** — 1–2 users on a single small
ArvanCloud VPS, no monitoring. Each choice below is safe for alpha but should be revisited before a real
clinic or larger load. Treat this as the **migration checklist**: when you move to a bigger server / real
users, walk the table and the fast-path at the bottom.

Companion to [production.md](production.md) (current shape) and
[production-readiness.md](production-readiness.md) (the safety gap list + go-live checklist).

## Trade-offs we made (and how to undo them)

| Area | Alpha choice (why) | Trade-off / risk | Scale-up action |
|---|---|---|---|
| **Topology** | Everything on one VPS (postgres, minio, redis, backend, ai-engine, frontend, caddy) | No isolation; one box = single point of failure; resource contention under load | Split data services + the ai-engine worker to their own nodes (architecture already separates them) |
| **Server size** | 2 vCPU / 2–4 GB + swap | Frontend build leans on swap (slow, OOM-prone); no headroom | 8 GB+; build images in CI/registry instead of on the box |
| **Image build** | `deploy.sh` builds on the box | Slow deploys; RAM spike is the main reason swap is needed | Build in CI → push to a registry → `pull` on the server |
| **Monitoring** | None (overlay deferred) | Blind to errors, queue depth, disk, cert expiry, backup freshness | Enable `docker-compose.monitoring.yml` (Prometheus/Grafana/GlitchTip/Uptime Kuma; ~2–3 GB) + alerts — see [monitoring.md](monitoring.md) |
| **Object storage** | Self-hosted MinIO, single node, local volume; backend uses the **MinIO root** key | App holds full storage admin; no replication; root-key leak = total media compromise | App-scoped key + server-side encryption + bucket versioning; or migrate to **ArvanCloud S3** (managed durability) — backend is S3-compatible, just swap endpoint+creds |
| **Backups** | Nightly encrypted pg dump, **local-only** (offsite off unless `OFFSITE_ALIAS` set) | Backups die with the box; media not mirrored | Set `OFFSITE_ALIAS` + `mc` → ArvanCloud S3; rehearse `restore.sh` monthly; mirror media |
| **Secrets** | `.env.prod` on the box, `scp` to move servers | Server is the only copy; no versioning/rotation/audit; losing `BACKUP_ENCRYPTION_KEY` = unrecoverable backups | Source-of-truth in a password manager (min) → **Ansible Vault**-templated `.env.prod` (fits our setup) → self-hosted Infisical/Vault at scale |
| **Auth tokens** | Refresh token in browser `localStorage` (needed so refresh-survives-reload works in prod) | XSS could exfiltrate the refresh token | Move the refresh token to a Secure **HTTP-only cookie** (backend-set); keep access token in memory |
| **TLS edge** | Option A direct-to-origin (Caddy on the box), no CDN | No caching/DDoS/WAF; single origin | Option B (ArvanCloud CDN in front, with a DPA for PHI) or a WAF; keep Caddy as origin TLS |
| **CI / quality gate** | None enforced on deploy | A broken commit can reach prod | CI on PRs (200 backend + 52 ai_engine tests + `tsc`) — `production-readiness.md` T7 |
| **Environments** | Deploy straight to prod | No safe place to test deploys | Add a staging stack (own DB/bucket) |
| **Resource limits** | No `mem_limit`/`cpus` set in prod compose | A runaway container can starve the box | Set per-service limits sized to the VPS (log rotation is already configured) |
| **Synthesis model** | `gpt-5.4-nano` (cheaper) | Eval golden set was validated on `gpt-5.4-mini`, not nano | Run `apps/ai_engine/eval/run_all.py` on nano; move to a validated/larger model if it regresses |
| **AI gateway** | Single EU instance | No redundancy; gateway down = no transcription/synthesis | HA gateway / failover; monitor reachability from the VPS |
| **ai-engine worker** | Single worker, default concurrency | Limited throughput under burst | Scale worker concurrency / move to its own node |
| **Postgres / Redis** | Default config, no pooling | Fine for low load; not tuned | Tuned configs + connection pooling; consider managed Postgres |

## Fast migration path (bigger server / real users)

When the time comes, roughly in this order:

1. **Provision** a larger VPS (8 GB+); prep it (`deploy/ansible/prepare-server.yml`), set a Docker registry mirror if needed.
2. **Secrets** into Ansible Vault (or a password manager) as the source of truth; stop relying on `scp`.
3. **Object storage:** switch to ArvanCloud S3 *or* give MinIO an app-scoped key + encryption + versioning.
4. **Backups:** turn on off-box (`OFFSITE_ALIAS` → ArvanCloud S3) and rehearse a restore.
5. **Monitoring + alerts:** bring up the monitoring overlay; wire alerts (errors, queue depth, disk, cert, backup freshness).
6. **CI gate** green on `main`; build images in CI and pull on the server.
7. **Staging** environment for deploy rehearsals.
8. **Synthesis model:** re-run evals; pick the model that meets quality at acceptable cost.
9. **Edge:** decide CDN/WAF (Option B + DPA) vs staying direct-to-origin.
10. **Resource limits** + Postgres tuning sized to the new box.

Nothing here blocks alpha — it's the deliberate debt list, kept so the jump to "real" is a checklist, not an archaeology project.
