# Backend Docs

Backend docs describe the as-built FastAPI backend.

## Documents

- [Backend design](design.md): Postgres metadata, MinIO artifacts, tenant scoping, patient-aware sessions and captures, Alembic migrations, and AI engine processing.
- [Authentication](auth.md): backend-managed JWT auth, low-friction development login, roles, tenants, and frontend contract.
- [Storage](storage.md): MinIO development and production object storage requirements.

## Direction

The backend keeps the capture-first product promise with durable database records and object storage instead of file-backed JSON metadata. Celery and Redis provide the processing boundary between backend and `apps/ai_engine`; worker behavior is documented in [AI engine docs](../ai_engine/README.md).
