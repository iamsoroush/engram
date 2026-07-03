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

## Boundaries

Celery and Redis are the processing boundary between the backend (producer) and `apps/ai_engine`
(worker); worker behavior is documented in [AI engine docs](../ai_engine/README.md). System-wide
structure and data flow: [architecture.md](../architecture.md).
