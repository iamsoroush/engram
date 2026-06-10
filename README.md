# Notari

Monorepo for Notari. Its first product, Memora, is a memory layer for aesthetics clinics.

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
cd notari
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

For full-stack development with both services in Docker:

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
- Redis: `localhost:6389`

Stop the development stack:

```sh
docker compose down
```

## Production

Production uses `docker-compose.prod.yml`.

The production stack includes:

- `backend`: FastAPI served by uvicorn inside a private Docker network
- `ai-engine`: background AI job worker
- `frontend`: nginx serving the built Vite app and proxying `/api/v1` to the backend

Only nginx is published to the host. The backend is reachable by other containers as `http://backend:8000`.

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
BACKEND_APP_NAME=Notari API
BACKEND_CORS_ORIGINS=["https://notari.example.com"]
BACKEND_DATABASE_URL=postgresql+psycopg://...
BACKEND_OBJECT_STORAGE_ENDPOINT=https://minio.internal:9000
BACKEND_OBJECT_STORAGE_BUCKET=notari-captures
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

```text
.
├── apps
│   ├── backend
│   │   ├── Dockerfile
│   │   ├── Dockerfile.prod
│   │   └── README.md
│   ├── ai_engine
│   │   ├── Dockerfile
│   │   ├── README.md
│   │   └── ai_engine
│   └── frontend
│       ├── Dockerfile
│       ├── Dockerfile.prod
│       ├── README.md
│       └── nginx.conf
├── docker-compose.yml
├── docker-compose.prod.yml
├── docs
│   ├── ai_engine
│   │   ├── README.md
│   │   └── processing.md
│   ├── backend
│   │   ├── auth.md
│   │   ├── storage.md
│   │   ├── v1-current.md
│   │   └── v2-design.md
│   ├── frontend
│   │   ├── auth-login.md
│   │   ├── sync-outbox.md
│   │   └── v1-current.md
│   ├── architecture.md
│   └── production.md
├── .env.example
└── README.md
```
