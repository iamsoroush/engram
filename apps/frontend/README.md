# Frontend

Vite + React frontend for Engram, clinical memory for aesthetics and therapy clinics.

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

Tests and guards:

```sh
npm run test:unit    # Vitest unit tests
npm run test:e2e     # Playwright e2e (hermetic, mocked API)
npm run i18n:guard   # fails on hardcoded chrome strings (see docs/frontend/i18n.md)
```

## Testing

Two Playwright layers, run by two different CI jobs (`.github/workflows/ci.yml`):

- **Hermetic** (`tests/e2e/`, `playwright.config.ts`) — the frontend runs for real, the API is mocked
  via `page.route` (`tests/e2e/_setup.ts`). Fast UI/i18n coverage, no backend. `npm run test:e2e`.
- **Real-stack** (`tests/e2e-stack/`, `playwright.stack.config.ts`) — the **merge gate**: the frontend
  drives the real backend + Celery + MinIO from the compose stack (nothing mocked), so the API
  contract, Alembic migrations, object storage, tier gating, and the public token pages are exercised
  on every merge. Helpers are in `tests/e2e-stack/_stack.ts`.

The real-stack suite has two tiers, both keyless:

- **P0** (`p0-*.spec.ts`) — merge-blocking, **gateway-less** and deterministic (`docker-compose.e2e.yml`
  forces no LLM gateway + synthesis off). AI stays deterministic via **fixture captures**: the
  filenames under `tests/e2e-stack/fixtures/` (e.g. `audio_01_initial_consultation.wav`) are
  load-bearing — the AI engine returns canned transcripts/captions for them with no gateway. Because
  the browser re-encodes/renames audio uploads, gateway-less audio fixtures are seeded through the
  `/captures` API (`uploadCaptureApi`), not the capture dialog.
- **P1** (`p1-*.spec.ts`) — main-merge only, adds a deterministic OpenAI-compatible **mock gateway**
  (`e2e-mock-gateway/mock_gateway.py`, wired by `docker-compose.e2e-ai.yml`) with synthesis enabled, so
  the structured report / treatments / safety-flags path runs end-to-end. The mock's canned payloads
  mirror the AI-engine synthesis fixtures (`apps/ai_engine/tests/test_report_synthesis.py`) so schema
  drift breaks the P1 job loudly.

Run the real-stack suite locally:

```sh
# From the repo root — bring up the deterministic gateway-less stack and wait for health:
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait

# Then run the P0 suite against it (default frontend port 5183):
cd apps/frontend
PLAYWRIGHT_BASE_URL=http://localhost:5183 npx playwright test --config playwright.stack.config.ts p0-
```

For P1, add the mock-gateway override and run the `p1-` files:

```sh
docker compose -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.e2e-ai.yml up -d --build --wait
PLAYWRIGHT_BASE_URL=http://localhost:5183 npx playwright test --config playwright.stack.config.ts p1-
```

Isolated worktree stacks run on non-default host ports — pass the matching `PLAYWRIGHT_BASE_URL` (and
port env vars to `docker compose`) so both stacks can coexist. The `tests/visual` snapshots stay
advisory (`npm run test:visual`).

## Source Layout

- `src/app`: root app orchestration, navigation, and session state helpers.
- `src/domain`: shared frontend types and UX status mapping.
- `src/features`: one module per feature area — see the directory for the current list (auth,
  capture, memory, aesthetics, qa, insights, therapy, …). Modules are presentational; API
  orchestration is threaded from `src/app`.
  - `src/features/aesthetics` holds the aesthetics-**Basic** surfaces (tier-gated, zero-AI). Story
    IDs (AES-###) resolve via [`../../docs/ux/aesthetics-stories.md`](../../docs/ux/aesthetics-stories.md);
    manual test script: [`../../docs/qa/aes-frontend-scenarios.md`](../../docs/qa/aes-frontend-scenarios.md).
- `src/services`: API client/normalizers and browser storage adapters.
- `src/shared`: reusable UI primitives, the `shared/i18n` chrome-translation seam, and small
  environment helpers.

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
