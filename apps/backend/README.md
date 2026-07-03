# Backend

FastAPI API server for Engram, the platform behind Engram (clinical memory for aesthetics and therapy clinics).

## Runtime

- Python 3.12+
- FastAPI
- uvicorn
- SQLAlchemy
- Alembic
- Postgres
- Redis

## URLs

When running through the development Compose stack:

- API base: `http://localhost:8010/api/v1`
- Docs: `http://localhost:8010/api/v1/docs`
- OpenAPI JSON: `http://localhost:8010/api/v1/openapi.json`
- Health: `http://localhost:8010/api/v1/health`

## API contracts

The OpenAPI schema (`/api/v1/openapi.json`) is the machine source of truth. The deterministic
aesthetics-Basic surfaces (smart search, duplicate guard, assign-later suggestion, last-visit, aftercare
templates) and the patient-facing surface (tokenized, revocable curated shares + the public read) have
their stable request/response contracts documented for the frontend in
[`docs/backend/aes-basic-api.md`](../../docs/backend/aes-basic-api.md); the Pro patient Q&A contracts
are in [`docs/backend/aes-pro-qa-api.md`](../../docs/backend/aes-pro-qa-api.md).

## Docker Development

From the repository root:

```sh
docker compose up --build backend
```

Open a backend shell:

```sh
docker compose exec backend bash
```

Run migrations manually from a backend shell:

```sh
alembic upgrade head
```

Stop services:

```sh
docker compose down
```

The backend source directory is mounted into the container and uvicorn runs with reload enabled.

## Local Development

Use local Python only if you specifically want local backend tooling.

```sh
cd apps/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

Then open:

```text
http://localhost:8010/api/v1/docs
```

## Environment

Backend settings use the `BACKEND_` prefix.

Common variables:

```sh
BACKEND_APP_NAME=Engram API
BACKEND_CORS_ORIGINS=["http://localhost:5183"]
BACKEND_AUTH_MODE=dev
BACKEND_JWT_SECRET=dev-only-change-me
BACKEND_DATABASE_URL=postgresql+psycopg://engram:engram@postgres:5432/engram
BACKEND_OBJECT_STORAGE_ENDPOINT=http://minio:9000
BACKEND_OBJECT_STORAGE_BUCKET=engram-captures
BACKEND_CELERY_BROKER_URL=redis://redis:6379/0
BACKEND_CELERY_RESULT_BACKEND=redis://redis:6379/1
BACKEND_AI_JOB_MAX_RETRIES=3
BACKEND_AI_JOB_RETRY_DELAY_SECONDS=30
BACKEND_AI_JOB_RETRY_MAX_DELAY_SECONDS=900
BACKEND_AI_JOB_DISPATCH_VISIBILITY_TIMEOUT_SECONDS=300
BACKEND_AI_JOB_RUNNING_STALE_SECONDS=900
BACKEND_AI_ENGINE_INTERNAL_TOKEN=dev-ai-engine-token
```

Development auth supports:

```sh
curl -X POST http://localhost:8010/api/v1/auth/dev-login \
  -H 'Content-Type: application/json' \
  -d '{"persona":"doctor"}'
```

For development Compose, root `.env` also controls:

```sh
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8010
```

## Production Image

Build the backend production image from the repository root:

```sh
docker compose -f docker-compose.prod.yml build backend
```

The production service is private to the Docker network. Public traffic reaches it through the frontend nginx container at `/api/v1`.

## AI Job Producer

The backend only creates durable job rows and sends named Celery tasks through Redis; it never executes AI work itself. The job types (per-capture processing, report synthesis, patient memory, Q&A drafts) are defined by `AiJobType` in `app/models.py`, and each type's Celery task name lives in `TASK_NAME_BY_JOB_TYPE` in `app/services/ai_jobs/orchestration.py`. Worker execution lives in `apps/ai_engine`, which calls protected backend `/internal/ai/...` endpoints to start, complete, retry, or fail jobs. Orchestration details: [`docs/backend/processing.md`](../../docs/backend/processing.md).

```sh
docker compose up --build backend ai-engine redis
```
