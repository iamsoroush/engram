# Backend structural-refactor plan

**Status:** proposal / not started. Plan only — no source changes made.
**Scope:** `apps/backend/app` structural debt. No behavior changes; every increment must keep the
public API and the test suite green.
**Owner:** unassigned. **Process doc** — fold durable outcomes into `docs/backend/` and delete when done.

Entry docs consulted: `docs/backend/README.md`, `CLAUDE.md` §6 (thin route/controller rule),
`.github/workflows/ci.yml` (the canonical test invocation).

---

## 1. Method & baseline

Measurements taken from the current tree (lines = `wc -l`):

| Area | Observation |
|---|---|
| `app/main.py` | **1189 lines, 81 route handlers** on two routers (`api_v1`, `internal_api`) spanning ~14 domains, all in one flat file with no section structure. |
| `app/jobs/` | **Dead.** Contains only `__pycache__/` (a fossil `tasks.cpython-313.pyc` + `__init__` pyc). No `.py` source. No repo-wide reference; `celery_app.py` has no `include`/autodiscover pointing at it. |
| `app/report_templates/` | **Dead.** Empty directory. No repo-wide reference. |
| `app/services/` | 33 flat modules + 2 subpackages (`ai_jobs/`, `ai_usage/`), 11.6k lines. A handful of god-modules: `services/qa.py` (1157), `services/ai_jobs/worker.py` (1203), `patient_memory.py` (759), `session_processing.py` (743). |
| `app/schemas/api.py` | 389 lines — a single grab-bag of request/response models across every domain. |
| Router wiring | **Inconsistent.** 4 domains already live in self-contained router files (`qa_api.py`, `insights_api.py`, `smart_lists_api.py`, `feedback_api.py`); the other ~14 domains sit inline in `main.py`. |

### The thin-routes rule is *already* satisfied — the debt is organizational

CLAUDE.md §6 says "keep route/controller layers thin." Spot-checking handlers
(`upload_capture`, the `captures/*`, `sessions/*`, and `internal/ai/jobs/*` routes) confirms they
**already delegate to services** — most are 3–10 lines that parse the request and call one service
function. So this is **not** a "fat controller" problem. The debt in `main.py` is **module size and
flat organization**: one 1189-line file mixing auth, sessions, captures, patients, worklist,
aftercare, shares, tenant/AI config, and the internal worker callback API. That size is the real
cost — it's the merge-conflict hot spot and the hardest file to navigate in the backend.

The fix is therefore low-risk: **finish the router-split pattern that already exists** for
qa/insights/smart-lists/feedback, extracting the inline domains into sibling router modules. No
logic moves; decorators and their thin bodies move verbatim.

---

## 2. Verification strategy (read this before touching routes)

**Critical gap:** the test suite (`tests/`) is **pure unit tests that import services directly**
(e.g. `from app.services.captures import ...`). **No test imports `app.main` or uses FastAPI
`TestClient`.** Consequence: moving route handlers between files is **not covered by the existing
tests** — a green suite does *not* prove the routes still wire up.

The canonical suite runs as (from `apps/backend/`, per `ci.yml`):

```sh
python -m unittest discover -s tests
```

Because that suite can't see route regressions, each router-moving increment must **additionally**
be gated by a cheap route/schema-invariance check. Recommended, in order of value:

1. **Import + route-table snapshot.** Before the first router increment, capture the sorted set of
   `(method, path)` from `app.main.app.routes` and assert it is byte-identical after each move. This
   is the single most valuable safety net for this refactor and should be **increment 0**.
2. **OpenAPI snapshot.** Capture `app.openapi()` (or just the `paths` keys + operation `tags`) and
   diff — catches path, tag, and response-model drift the route-table check misses.
3. **A thin smoke test** hitting `/api/v1/health` via `TestClient` to prove the app object still
   constructs and mounts. (Adds `httpx` as a test dep if not present — confirm before assuming.)

Items 1–2 can live as one new `tests/test_route_surface.py` — a genuine, durable addition (not
throwaway), since it will keep guarding the route surface after this refactor. It closes the
observed coverage gap and belongs in the suite permanently.

---

## 3. Sequenced increments

Ordered smallest-blast-radius first. Each is independently shippable and independently revertible.
"Verify" is what proves the increment safe **beyond** the suite passing.

### Increment 0 — Route-surface guard (enables everything below)
- **Do:** add `tests/test_route_surface.py` asserting the `(method, path)` set and OpenAPI `paths`
  match a checked-in snapshot generated from `main` before any move.
- **Why first:** every route move in §3 is verified against it. No product code changes.
- **Verify:** `python -m unittest discover -s tests` green; snapshot committed.
- **Risk:** none (test-only).

### Increment 1 — Delete dead directories
- **Do:** remove `app/jobs/` and `app/report_templates/`. (`app/jobs/__pycache__` holds only a stale
  compiled `tasks.pyc` with no surviving source.)
- **Why:** zero references anywhere in the repo (grepped `.py`/yml/ini/Dockerfile + celery config);
  they read as live modules and mislead navigation.
- **Verify:** repo-wide grep for `report_templates`, `app.jobs`, `app/jobs`, `jobs.tasks` returns
  nothing (already true); suite green; app imports.
- **Risk:** negligible. Also add `**/__pycache__/` hygiene note if pyc fossils recur.

### Increment 2 — Extract local file helpers out of `main.py`
- **Do:** move `ranged_file_response()` and `parse_metadata_form()` (currently module-level in
  `main.py`, ~lines 168–214) into a small `app/http/responses.py` (or `app/api/_forms.py`). They are
  pure functions with unit-testable branches (the 416/206 byte-range logic especially).
- **Why:** they're reusable HTTP plumbing, not routing; extracting them lets you add direct unit
  tests for the range logic that currently has no coverage.
- **Verify:** import updated in `main.py`; new unit tests for range parsing (416/206/full-body);
  suite green.
- **Risk:** low; contained, and now test-covered.

### Increment 3 — Extract the internal worker-callback router
- **Do:** move the 7 `internal_api` routes (`/internal/ai/jobs/*` + `/internal/captures/{id}/
  file-content`) into `app/internal_api.py`, mirroring the existing self-contained-router pattern
  (`qa_internal_api` already sets this precedent). Keep the `require_ai_engine_token` dependency and
  `include_in_schema=False` on the router.
- **Why:** this is a distinct trust boundary (AI-engine → backend) and a clean, self-contained seam
  — the lowest-risk domain to peel off first.
- **Verify:** route-surface snapshot (increment 0) byte-identical; the AI-job retry/recovery unit
  tests (`test_ai_jobs_retry.py`) still pass; suite green.
- **Risk:** low.

### Increment 4 — Extract remaining inline domains into routers, one per PR
Peel these out of `main.py` in this order (each its own commit, each verified against increment 0):

1. `auth_api.py` — `/auth/*` + `/me` (7 routes; complements the existing `app/auth/` service package).
2. `tenant_config_api.py` — `/ai-usage*`, `/ai-config/models`, `/tenant/settings`, `/clinic/plan`.
3. `sessions_api.py` — `/sessions/*` incl. therapy sub-routes, `/ai-jobs/*`.
4. `captures_api.py` — `/captures/*` + the two capture-upload routes.
5. `patients_api.py` — `/patients/*`, `/patient-memory*`.
6. `worklist_api.py`, `aftercare_api.py`, `shares_api.py` (`/patient-shares/*` + public `/share/*`),
   `team_api.py` (`/clinic/members`, `/clinic/team*`).

After all extractions, `main.py` should retain **only** app construction: `FastAPI(...)`, CORS,
Sentry/Prometheus instrumentation, the `/health` route, and the `include_router(...)` wiring —
targeting roughly ~150 lines.
- **Why:** finishes the established pattern; turns the merge-hot-spot into small domain files.
- **Verify (each):** route-surface + OpenAPI snapshot identical; suite green; app imports.
- **Risk:** low but repetitive — the snapshot guard is what makes it mechanical rather than scary.

### Increment 5 — Split `schemas/api.py` by domain (optional, do after routers)
- **Do:** split the 389-line grab-bag into `app/schemas/{sessions,captures,patients,tenant,...}.py`
  mirroring the new router modules; re-export from `app/schemas/__init__.py` (or `api.py`) so
  existing `from app.schemas.api import X` imports keep working during migration, then update imports.
- **Why:** the schema file will otherwise stay a shared-edit bottleneck once routers are split.
- **Verify:** suite green; OpenAPI component schemas unchanged (snapshot).
- **Risk:** low; do it *after* routers so schema homes match router homes.

### Increment 6 — Break up service god-modules (separate, later effort)
Larger and higher-risk than routing; **explicitly deferred** and scoped as its own initiative, not
bundled with the routing work. Candidates, by size and by whether tests give cover:
- `services/qa.py` (1157) — split draft/revise/thread/inbox concerns; **note:** `qa_draft`/`qa_revise`
  have **no evals** (known debt per `docs/ai_engine/evals.md`) and `test_patient_qa.py` is the only
  guard — treat as higher-risk.
- `services/ai_jobs/worker.py` (1203) — this is an **AI-job** module: any change here is **eval-gated**
  (CLAUDE.md §4 — run `apps/ai_engine/eval/run_all.py`, no regressions). Do not fold into the routing PRs.
- `patient_memory.py` (759), `session_processing.py` (743) — split along the seams already implied by
  their function groups; covered by `test_patient_memory_intelligence.py`, `test_organizing_state.py`,
  `test_live_report.py`.

Because these carry real logic (and some are eval-gated), they are **out of scope for the mechanical
routing refactor** and should each get their own plan with the relevant eval/unit gate identified up
front.

---

## 4. Non-goals / explicitly out of scope
- No endpoint additions, removals, renames, or response-shape changes. The route surface is invariant
  through increments 0–5 (that's what the snapshot enforces).
- No behavior change to any service. No AI-job logic changes in this plan (those are eval-gated and
  deferred to increment 6's follow-ups).
- No dependency, config, Alembic, or Docker changes (except deleting the two dead dirs).

## 5. Close-the-loop checklist (per CLAUDE.md §3)
- Behavior changed? **No** — so no `docs/ux/` update expected.
- Boundaries/data changed? The router file layout changes; if `docs/backend/README.md` or
  `docs/architecture.md` describe "routes live in `main.py`", update them to the new module map when
  increments 3–4 land.
- Decision made? If we adopt "one router module per domain; `main.py` is wiring-only" as a standing
  convention, record it in `docs/technical-decisions.md`.
- AI job touched? Only in the deferred increment 6 — that work runs the eval suite; the routing work
  does not touch AI jobs.
- Doc added/deleted? Fold this plan's durable outcome (the module map + the route-surface test) into
  `docs/backend/` and **delete this file** when the routing increments finish.
- `python3 scripts/check-doc-links.py` before declaring done.
