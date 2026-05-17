# Production

## Current Production Shape

Production uses:

```text
docker-compose.prod.yml
```

Services:

- `frontend`: nginx serving the built Vite app and proxying `/api/v1` to backend.
- `backend`: FastAPI/uvicorn service private to the Docker network.
- `ai-engine`: background capture processing worker private to the Docker network.
- `redis`: broker/result backend for Celery.
- `postgres`: metadata store for backend v2.
- `minio`: S3-compatible object storage for backend v2.

Only the frontend/nginx service is published to the host. The backend is reachable inside Docker as:

```text
http://backend:8000
```

## API Routing

In production, leave `PROD_VITE_API_URL` empty for the default same-origin setup. The browser calls:

```text
/api/v1/...
```

nginx proxies those requests to the backend container. This avoids CORS issues and avoids phone/LAN problems where `localhost` would refer to the client device.

## Capture Storage

Production Compose defines:

```text
capture_data:/data/captures
```

This is acceptable for prototype deployments but not enough for real clinical production. For production-grade durability, move source files to object storage and metadata to a database.

Backend v2 target:

- Postgres stores tenants, users, patients, sessions, captures, artifacts, audit events, and processing job rows.
- MinIO stores source files and generated artifacts.
- MinIO remains the production object storage target; do not switch production back to backend-local files.
- Celery and Redis own background job execution. Current capture processors are placeholders until real AI logic is implemented.

## Data Safety

The product promise is that captures are not lost because the network is slow.

Current safety layers:

- Browser IndexedDB pending outbox before upload.
- Retry mechanism for failed uploads.
- Browser warning while unsynced captures exist.
- Backend-mounted volume after upload succeeds.
- Synced browser cache for fast preview, evictable after backend safety.

Backend v2 safety boundary:

- A capture is safely transferred only after the source object exists in MinIO and its metadata is committed in Postgres.
- If either side fails, the API must not return successful upload.
- Browser pending outbox data remains the safety copy until backend success.

Important distinction:

- Unsynced browser outbox data is the safety copy and must not be silently deleted.
- Synced browser cache is only a convenience and may be evicted.

## HTTPS Requirement

Real deployment should use HTTPS. This is especially important for:

- microphone access through `MediaRecorder`;
- camera access in some browser/device combinations;
- protected clinical data in transit;
- service worker/offline capabilities if added later.

For local LAN testing over HTTP, audio capture may fall back to file input.

## Environment Variables

Backend:

```sh
BACKEND_APP_NAME=AesMem API
BACKEND_CORS_ORIGINS=["https://aesmem.example.com"]
BACKEND_AUTH_MODE=production
BACKEND_DATABASE_URL=postgresql+psycopg://...
BACKEND_OBJECT_STORAGE_ENDPOINT=https://minio.internal:9000
BACKEND_OBJECT_STORAGE_BUCKET=aesmem-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=...
BACKEND_OBJECT_STORAGE_SECRET_KEY=...
BACKEND_OBJECT_STORAGE_SECURE=true
BACKEND_CELERY_BROKER_URL=redis://redis:6379/0
BACKEND_CELERY_RESULT_BACKEND=redis://redis:6379/1
BACKEND_AI_JOB_MAX_RETRIES=3
BACKEND_AI_JOB_RETRY_DELAY_SECONDS=30
AI_ENGINE_INTERNAL_TOKEN=...
```

Frontend production build:

```sh
PROD_FRONTEND_PORT=80
PROD_VITE_API_URL=
```

Leave `PROD_VITE_API_URL` empty when nginx proxies `/api/v1` on the same origin.

## Operational Concerns

Before handling real clinical data, production needs:

- TLS termination and secure headers;
- authentication and role-based authorization;
- tenant/clinic isolation;
- encrypted Postgres and MinIO storage;
- backups and restore drills;
- audit logging;
- file retention policy;
- upload size limits;
- monitoring for failed uploads, failed/retried Celery jobs, Redis health, Postgres capacity, and MinIO capacity;
- structured logs and request IDs;
- migration path from file-backed prototype data to database/object storage.

## MinIO Security

Production MinIO requirements:

- Keep MinIO API and console on a private network.
- Do not enable public bucket access.
- Use separate backend app and operational admin credentials.
- Limit backend credentials to required buckets and prefixes.
- Enable server-side encryption.
- Use bucket versioning where practical.
- Document lifecycle and retention policy before real clinical use.
- Serve previews through backend authorization or short-lived presigned URLs.
- Back up MinIO object data together with Postgres metadata.

## Authentication

Production authentication is backend-managed JWT auth. Nginx must not be the authorization boundary for `/api/v1`; it should proxy requests to the backend after handling TLS and security headers.

Development can use `BACKEND_AUTH_MODE=dev` and `POST /api/v1/auth/dev-login` with seeded personas. Production must disable dev login.

## Deployment Commands

Build and start:

```sh
docker compose -f docker-compose.prod.yml up --build -d
```

Health:

```sh
curl http://localhost/api/v1/health
```

Stop:

```sh
docker compose -f docker-compose.prod.yml down
```

If port 80 is unavailable:

```sh
PROD_FRONTEND_PORT=8080 docker compose -f docker-compose.prod.yml up --build -d
```
