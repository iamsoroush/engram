# Engram

Monorepo for **Engram** — capture-first clinical memory, currently for aesthetics clinics (therapy and dermatology are the next verticals).

## Apps

- `apps/backend`: FastAPI API server. See [apps/backend/README.md](apps/backend/README.md).
- `apps/ai_engine`: Celery worker for AI processing jobs. See [apps/ai_engine/README.md](apps/ai_engine/README.md).
- `apps/frontend`: Vite + React frontend. See [apps/frontend/README.md](apps/frontend/README.md).

## Prerequisites

- Docker + Docker Compose
- Node.js 22+
- Python 3.12+
- Git

Recommended:

- VS Code
- VS Code Dev Containers extension
- Docker Desktop on macOS/Windows

## Initial Setup

```sh
git clone <repo-url>
cd engram
cp .env.example .env
```

## Development

Use the app-specific READMEs for day-to-day development:

- Backend workflow: [apps/backend/README.md](apps/backend/README.md)
- AI engine workflow: [apps/ai_engine/README.md](apps/ai_engine/README.md)
- Frontend workflow: [apps/frontend/README.md](apps/frontend/README.md)

Use the engineering docs for architecture and design decisions:

- [docs/README.md](docs/README.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/frontend/README.md](docs/frontend/README.md)
- [docs/backend/README.md](docs/backend/README.md)
- [docs/production.md](docs/production.md)

**Recommended — `scripts/dev-stack.sh` is the default way to bring up the dev stack.** It provisions an isolated stack and supports **multi-worktree development**: each git worktree gets its own database, bucket, and host ports (the database is cloned from the canonical data, so you inherit real data to test against).

```sh
scripts/dev-stack.sh up      # provision + start; prints this stack's app/API URLs
scripts/dev-stack.sh down    # stop (add --data to also drop this stack's DB + bucket)
```

See [docs/dev/worktree-stacks.md](docs/dev/worktree-stacks.md) for details. Inside a **git worktree** you must use this script (not the root `docker compose up`) to avoid host-port/DB collisions with other stacks.

Alternatively, for a single self-contained stack in the **primary checkout**:

```sh
docker compose up --build
```

Docker Compose automatically reads variables from the repo-root `.env` file. Start from `.env.example`, then keep local-only values there:

```sh
cp .env.example .env
```

For example, when testing the Vite dev server through an HTTPS tunnel such as ngrok, set the tunnel host in `.env`:

```sh
VITE_ALLOWED_HOSTS=example.ngrok-free.dev
```

Services:

- Frontend: `http://localhost:5183`
- Backend API: `http://localhost:8010/api/v1`
- Backend docs: `http://localhost:8010/api/v1/docs`
- MinIO (object storage): `localhost:9010` (console `localhost:9011`)
- Redis: `localhost:6389`

Stop the development stack:

```sh
docker compose down
```

## Production

Production uses `docker-compose.prod.yml` (plus the TLS overlay `docker-compose.prod.tls.yml` on the
real deployment). The stack runs `backend`, `ai-engine`, `frontend` (nginx), `postgres`, `minio`, and
`redis` on a private Docker network. The real deploy path is `scripts/bootstrap.sh` → `scripts/deploy.sh`
— see [docs/production.md](docs/production.md) for the authoritative setup, env vars, backups, and
operational notes; the commands below are for a local production-like run.

### Production Files

- `docker-compose.prod.yml`: production Compose stack
- `apps/backend/Dockerfile.prod`: backend production image
- `apps/ai_engine/Dockerfile`: AI engine worker image
- `apps/frontend/Dockerfile.prod`: frontend build and nginx runtime image
- `apps/frontend/nginx.conf`: static file serving and API proxy config

### Environment

Copy the example environment file and adjust values:

```sh
cp .env.example .env
```

Important production variables:

```sh
BACKEND_APP_NAME=Engram API
BACKEND_CORS_ORIGINS=["https://engram.example.com"]
BACKEND_DATABASE_URL=postgresql+psycopg://...
BACKEND_OBJECT_STORAGE_ENDPOINT=https://minio.internal:9000
BACKEND_OBJECT_STORAGE_BUCKET=engram-captures
BACKEND_CELERY_BROKER_URL=redis://redis:6379/0
BACKEND_CELERY_RESULT_BACKEND=redis://redis:6379/1
AI_ENGINE_INTERNAL_TOKEN=change-me
PROD_FRONTEND_PORT=80
PROD_VITE_API_URL=
```

Leave `PROD_VITE_API_URL` empty in the default production setup so the browser calls `/api/v1/...` on the nginx origin.

### Start Production

```sh
docker compose -f docker-compose.prod.yml up --build -d
```

Open:

- App: `http://localhost`
- API docs: `http://localhost/api/v1/docs`
- Health: `http://localhost/api/v1/health`

If port `80` is already in use:

```sh
PROD_FRONTEND_PORT=8080 docker compose -f docker-compose.prod.yml up --build -d
```

### Stop Production

```sh
docker compose -f docker-compose.prod.yml down
```

## Project Structure

Apps live under `apps/` (`backend`, `ai_engine`, `frontend` — each with its own README), deploy and
dev tooling under `scripts/` and `deploy/`, and engineering docs under `docs/`. The documentation map
in [CLAUDE.md](CLAUDE.md) §2 is the single index of all docs.
