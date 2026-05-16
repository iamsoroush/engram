# Backend Docs

Backend docs are split between the current prototype and the next backend design.

## Documents

- [Current prototype](v1-current.md): existing FastAPI API, local file storage, and prototype limits.
- [Backend v2 design](v2-design.md): Postgres metadata, MinIO artifacts, tenant scoping, patient-aware sessions and captures, and fake processing.
- [Authentication](auth.md): backend-managed JWT auth, low-friction development login, roles, tenants, and frontend contract.
- [Storage](storage.md): MinIO development and production object storage requirements.
- [Fake processing](fake-processing.md): fake job rows and generated placeholder outputs for transcripts, OCR, summaries, and organization.

## Direction

Backend v2 should preserve the capture-first product promise while replacing file-backed JSON metadata with durable database records and object storage. Celery, Redis, and real AI jobs are intentionally out of scope for this version.
