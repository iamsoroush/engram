# Backend Docs

As-built docs for the FastAPI backend. The OpenAPI schema (`/api/v1/openapi.json`) is the machine
source of truth for exact API contracts; these docs carry the model, semantics, and the stable
human contracts the frontend builds against.

## Documents

- [Data model](data-model.md): Postgres tables and enums, session/capture state semantics,
  idempotency, upload safety, and the audit trail.
- [Processing](processing.md): AI-job orchestration — dispatch chokepoints, the deterministic
  live-report rebuild, Pro synthesis gating + debounce, fair-use deferral, recovery sweeps, and
  tier gating.
- [Authentication](auth.md): backend-managed JWT auth, registration, dev login, roles, member
  management, and the frontend contract.
- [Storage](storage.md): MinIO object storage — development and production requirements, object
  keys, upload safety, and backup.
- [Aesthetics-Basic API](aes-basic-api.md): stable contracts for the deterministic zero-AI Basic
  surfaces (smart search, duplicate guard, last-visit, aftercare templates, patient shares,
  multi-seat).
- [Aesthetics-Pro Q&A API](aes-pro-qa-api.md): stable contracts for the Pro post-session
  patient↔clinic Q&A (threads, inbox, drafts, public surface).
- [Insights + feedback](insights-feedback.md): owner/admin clinic analytics and the AI-quality
  feedback harvester.

## Code layout

`app/main.py` is **wiring-only**: it builds the `FastAPI` app (Sentry, Prometheus, CORS), exposes
`/health`, and mounts routers. It contains no request logic. Every domain is a **self-contained
`APIRouter` in `app/<domain>_api.py`** whose thin handlers delegate to `app/services/*`:

- `auth_api` (`/auth/*`, `/me`), `tenant_config_api` (AI usage/model config, tenant settings,
  clinic plan), `patients_api`, `sessions_api` (+ therapy sub-plane, `/ai-jobs/*`), `captures_api`,
  `worklist_api`, `aftercare_api`, `shares_api` (tenant shares + public `/share/*`), `team_api`.
- `internal_api` — the AI-engine→backend worker-callback boundary (`/internal/*`, token-auth,
  hidden from the schema). Pre-existing self-contained routers: `qa_api`/`qa_internal_api`,
  `smart_lists_api`, `feedback_api`, `insights_api`.

Request/response models live in **per-domain `app/schemas/<domain>.py`**; `app/schemas/api.py` is a
backward-compatible re-export aggregator (new code imports from the domain module). Reusable HTTP
plumbing (byte-range media responses, multipart metadata parsing) lives in `app/http/`.

**Route-surface guard:** `tests/test_route_surface.py` snapshots every mounted route
(path/methods/`include_in_schema`/declared dependencies) and the OpenAPI paths against
`tests/route_surface_snapshot.json`. The rest of the suite imports services directly and never
builds the app, so this test is what catches a mis-wired or auth-changed route. Regenerate the
snapshot for an intentional endpoint change with `python -m tests.regen_route_surface`.

## Boundaries

Celery and Redis are the processing boundary between the backend (producer) and `apps/ai_engine`
(worker); worker behavior is documented in [AI engine docs](../ai_engine/README.md). System-wide
structure and data flow: [architecture.md](../architecture.md).
