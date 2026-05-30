# Frontend

Vite + React frontend for AesMem, a memory layer for aesthetics clinics.

## Runtime

- Node.js 22+
- Vite
- React
- nginx in production

## URLs

When running through the development Compose stack:

- Frontend: `http://localhost:5183`
- Backend API: `http://localhost:8010/api/v1`
- Backend docs: `http://localhost:8010/api/v1/docs`

## Recommended Development

For frontend-focused work, run the backend in Docker and run Vite locally.

From the repository root:

```sh
docker compose up --build backend
```

In another terminal:

```sh
cd apps/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5183
```

Vite proxies `/api/v1` to `http://localhost:8010`, so the app can use the same relative API path as production.

## Full Docker Development

From the repository root:

```sh
docker compose up --build frontend
```

The frontend source directory is mounted into the container and Vite runs with hot reload.

## Commands

Install dependencies:

```sh
npm install
```

Start Vite locally:

```sh
npm run dev
```

Build the frontend:

```sh
npm run build
```

Preview the production build locally:

```sh
npm run preview
```

## Source Layout

- `src/app`: root app orchestration, navigation, and session state helpers.
- `src/domain`: shared frontend types and UX status mapping.
- `src/features`: auth, capture, memory, and shell feature modules.
- `src/services`: API client/normalizers and browser storage adapters.
- `src/shared`: reusable UI primitives and small environment helpers.

## Environment

The frontend reads `VITE_API_URL`.

For the default local workflow, leave it unset and use the Vite proxy. If you want the browser to call the backend directly instead of proxying through Vite:

```sh
VITE_API_URL=http://localhost:8010/api/v1
```

In production, leave `PROD_VITE_API_URL` empty unless the API is hosted on another origin. With the default production setup, the browser calls `/api/v1/...` on the same origin and nginx proxies those requests to the backend container.

### HTTPS tunnel for phone testing

When using ngrok or another HTTPS tunnel against the Vite dev server, add the tunnel host to Vite's allowed host list:

```sh
VITE_ALLOWED_HOSTS=persuader-elective-capsize.ngrok-free.dev docker compose up frontend
```

For multiple hosts, separate them with commas.

## Production Image

Build the frontend production image from the repository root:

```sh
docker compose -f docker-compose.prod.yml build frontend
```

The production image builds the Vite app with Node.js, then serves the static files from nginx using `nginx.conf`.
