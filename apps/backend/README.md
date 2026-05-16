# Backend

FastAPI API server for AesMem, a memory layer for aesthetics clinics.

## Runtime

- Python 3.12+
- FastAPI
- uvicorn
- SQLAlchemy
- Alembic
- Postgres

## URLs

When running through the development Compose stack:

- API base: `http://localhost:8000/api/v1`
- Docs: `http://localhost:8000/api/v1/docs`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`
- Health: `http://localhost:8000/api/v1/health`

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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

```text
http://localhost:8000/api/v1/docs
```

## Environment

Backend settings use the `BACKEND_` prefix.

Common variables:

```sh
BACKEND_APP_NAME=AesMem API
BACKEND_CORS_ORIGINS=["http://localhost:5173"]
BACKEND_AUTH_MODE=dev
BACKEND_JWT_SECRET=dev-only-change-me
BACKEND_DATABASE_URL=postgresql+psycopg://aesmem:aesmem@postgres:5432/aesmem
BACKEND_OBJECT_STORAGE_ENDPOINT=http://minio:9000
BACKEND_OBJECT_STORAGE_BUCKET=aesmem-captures
```

Development auth supports:

```sh
curl -X POST http://localhost:8000/api/v1/auth/dev-login \
  -H 'Content-Type: application/json' \
  -d '{"persona":"doctor"}'
```

For development Compose, root `.env` also controls:

```sh
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

## Production Image

Build the backend production image from the repository root:

```sh
docker compose -f docker-compose.prod.yml build backend
```

The production service is private to the Docker network. Public traffic reaches it through the frontend nginx container at `/api/v1`.
