# Backend Docs

Backend docs are split between the current prototype and the next backend design.

## Documents

- [Current prototype](v1-current.md): existing FastAPI API, local file storage, and prototype limits.
- [Backend v2 design](v2-design.md): Postgres metadata, MinIO artifacts, tenant scoping, patient-aware sessions and captures, and AI engine processing.
- [Authentication](auth.md): backend-managed JWT auth, low-friction development login, roles, tenants, and frontend contract.
- [Storage](storage.md): MinIO development and production object storage requirements.
- [AI processing](ai-processing.md): current AI engine placeholder capture and session processors.

## Direction

Backend v2 should preserve the capture-first product promise while replacing file-backed JSON metadata with durable database records and object storage. Celery and Redis now provide the processing boundary between backend and `apps/ai_engine`; real AI job bodies are still intentionally out of scope.
