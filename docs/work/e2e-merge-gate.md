# E2E merge gate — real-stack Playwright suite (Basic + Pro)

**Fold destination:** a short "Testing" section in `docs/frontend/README.md` + a CI note in
`docs/production.md` once built; then delete this doc.

Goal: e2e tests that run on every merge to main against the **real compose stack**, covering both
aesthetics tiers, with zero LLM keys in CI. The existing hermetic suite (`apps/frontend/tests/e2e/`,
fully mocked API) stays as the fast UI/i18n layer; this adds `apps/frontend/tests/e2e-stack/`.

## Current state

- Hermetic Playwright suite: 10 specs (~38 tests), all API calls mocked via `tests/e2e/_setup.ts`;
  `playwright.config.ts` starts Vite at 127.0.0.1:5183; supports `PLAYWRIGHT_BASE_URL`.
- CI (`.github/workflows/ci.yml`, PR + push-to-main): backend/ai-engine unittest, frontend
  typecheck + vitest + i18n:guard, hermetic e2e, prod-compose validate, doc-links.
- Gap: **no test runs the frontend against the real backend** — API contract, Alembic migrations,
  MinIO upload, Celery pipeline, real tier gating, and public token pages are unexercised per merge.

## Determinism seams (verified)

1. **Basic tier = zero AI jobs** (`apps/backend/app/services/capabilities.py`: aesthetics `basic` →
   empty capability set). Basic capture is pure CRUD.
2. **Fixture captures**: filenames in `TEST_CAPTURE_TEXT_BY_FILENAME`
   (`apps/ai_engine/ai_engine/processing.py:67`, detection `is_fixture_capture` :931) yield canned
   transcripts/captions with **no gateway** (e.g. `audio_01_initial_consultation.wav`,
   `photo_01_pre_correction_left_cheek.jpg`).
3. **Gateway-less fallbacks**: `AI_ENGINE_TRANSCRIPTION_BASE_URL` unset (default) → notes
   passthrough, non-fixture photos blank caption, synthesis emits a skip sentinel (deterministic
   baseline report stands), patient-memory/Q&A jobs return the backend-supplied
   `deterministicFallback`.
4. **Synthesis gate**: `BACKEND_REPORT_SYNTHESIS_ENABLED` default false → synthesis never
   dispatched (`apps/backend/app/services/ai_jobs/reports.py` `session_synthesis_enabled`).
5. **Dev login**: `POST /api/v1/auth/dev-login` (personas doctor/assistant/admin/patient-preview +
   `tier` field → basic/pro/therapy demo tenants; gated on `BACKEND_AUTH_MODE=dev`, the compose default).
6. **Real registration**: `POST /api/v1/auth/register` mints an isolated Basic tenant + owner (no
   email verification); tier flips via the clinic-plan endpoint (owner/admin) — per-test isolation.
7. **Other dev seams**: `POST /api/v1/ai-usage/dev/set` (jump usage %), safety-flag rejection
   endpoint, share create + public `GET /share/{token}`.
8. Root `docker compose up` works with zero secrets; backend runs `alembic upgrade head` on boot.
9. Celery task names for log assertions: `ai_engine.process_{audio,text,image}_capture`,
   `process_session`, `process_patient_memory`, `process_qa_draft`, `process_qa_revise`.

## P0 — merge-blocking (gateway-less; target ≤ 15 min job incl. build)

Conventions: fresh tenant per test file via `/auth/register` (run-unique email), upgrade to Pro via
the plan endpoint where needed; dev-login demo tenants only for multi-persona tests (serialized,
run-unique patient names, never delete demo data); pin app language to `en` except i18n tests; no
fixed sleeps — auto-retrying `expect`/`expect.poll` (30s cap); fixture filenames are load-bearing.

| # | Scenario | Tier | Assertions (essence) |
|---|---|---|---|
| P0-1 | Register → onboarding → shell | Basic | 201; tier-accurate Basic tour (no AI claims); shell + clinic name |
| P0-2 | Basic zero-AI capture spine | Basic | note instant + editable; photo thumbnail **no caption/spinner**; audio = voice memo **no transcript**; no AI chrome outside Try-Pro teasers |
| P0-3 | Patient create + duplicate guard + Persian search | Basic | amber duplicate warning never blocks; `سارا` search hits with match-reason chips |
| P0-4 | Capture unassigned → assign later | Basic | Needs-input resolver, deterministic suggestion chip, lands on timeline |
| P0-5 | Share lifecycle + withholding | Basic | `/share/<token>` renders curated read-only; no national ID/internal/lots; revoked ≡ bogus ("no longer available"); raw capture URL → 401 |
| P0-6 | Tier-gating matrix | both | Basic: no Lists tab, `/smart-lists/*` + `/insights/treatments` + `/patient-qa/*` → 403; Pro: Lists tab + audio-first footer |
| P0-7 | Pro fixture-audio pipeline | Pro | processing state resolves; transcript == fixture text, editable, AI-vs-edited attribution; fixture caption; deterministic report contains content |
| P0-8 | Capture undo | Pro | delete newest capture → report reverts to exact prior state; others intact |
| P0-9 | Q&A ask → inbox → deterministic draft → send | Pro | public `/qa/<token>` question → pending in inbox with fallback draft; nothing auto-sends; reply visible to patient |
| P0-10 | Reception worklist multi-seat | Basic | assistant lines up patient → doctor sees + starts visit; worklist never blocks fresh capture |
| P0-11 | Non-owner edit block | Basic | default role permissions block editing another's capture, predictable error |
| P0-12 | Existing hermetic suite | both | unchanged, stays in the gate |

## P1 — main-merge (adds mock LLM gateway; separate job)

A ~80-line OpenAI-compatible mock (`POST /v1/chat/completions` + transcription route) in a compose
override, returning canned JSON keyed by prompt markers. **Derive canned synthesis payloads from
`apps/ai_engine/tests/test_report_synthesis.py` / `test_qa_draft.py` / `test_patient_memory_job.py`
fixtures so schema drift breaks loudly.** Env: `AI_ENGINE_*_BASE_URL=http://mock-gateway:9099/v1`,
`BACKEND_REPORT_SYNTHESIS_ENABLED=true`.

Scenarios: structured treatments table (B2.1); report-never-blanks on update (B5.2, mock adds
delay); verify bar + dose confirm persistence (B5.3/5.4); safety flags surface + rejection persists
across re-synthesis (B6.x); undo reverts AI-created patient (B7.1); smart lists + lot recall on real
synthesized data incl. "Similar lots (not included)" (B9.x); AI-usage limit UI via `/ai-usage/dev/set`
(95% notice, 101% degradation); Insights (owner-gated; Treatments Pro-only); team add/role change;
plan switch Basic→Pro; last-visit strip + prefill-not-autosaved; aftercare-template CRUD → share sheet.

## Infra

- New CI job `e2e-stack` (PR + main): `docker compose up -d --wait` + small
  `docker-compose.e2e.yml` override (`AI_ENGINE_MOCK_STAGE_DELAY_SECONDS=0.1`,
  `BACKEND_AUTH_MODE=dev`, `BACKEND_REPORT_SYNTHESIS_ENABLED=false`); GHA docker layer cache;
  `PLAYWRIGHT_BASE_URL=http://localhost:5183 npx playwright test tests/e2e-stack`; on failure upload
  Playwright report + `docker compose logs backend ai-engine`.
- Job `e2e-stack-ai` (push-to-main only, or nightly): same + mock gateway, runs P1.
- Stack project: `retries: 1`, `trace: retain-on-failure`, `workers: 2-3` (per-tenant isolation;
  shared-tenant specs serial).

## Non-goals

LLM output quality (eval suite owns it — never assert AI wording, only plumbing/placement); real
mic/camera + ghost overlay (manual QA); pixel-visual baselines (`tests/visual` stays advisory);
wall-clock expiry (SQL fixture or manual); load/backup/monitoring.

## Open details for the implementer

1. Confirm the clinic-plan endpoint verb from OpenAPI (PATCH vs PUT).
2. Verify whether the gateway-less fixture transcript triggers the AI patient-assignment gate for
   the undo-reverts-AI-patient scenario, or whether it needs the mock gateway (move it to P1 if so).
3. Do not touch `eval.yml` or the eval suite — different gate, different purpose.
