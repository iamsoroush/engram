# CLAUDE.md

This repository is developed with AI coding agents.

**Naming:** the platform and product share a single brand — **Engram** — used everywhere: repo, services, infra, API, and all customer-facing surfaces. Engram is capture-first clinical memory, currently for aesthetics clinics (therapy and dermatology are the next verticals).

Use this file as the starting guide. Do not read the whole repository blindly. Start from the relevant README/docs, then inspect only the files needed for the task.

---

## 1. First step by task type

### Frontend

Read:

- `README.md`
- `apps/frontend/README.md`

If the task changes visible behavior, also read:

- `docs/ux/overview.md`
- relevant files under `docs/ux/workflows/` or `docs/ux/screens/`

### Backend

Read:

- `README.md`
- `apps/backend/README.md`

If backend behavior affects users, also read:

- `docs/ux/overview.md`
- relevant workflow/screen docs

### AI Engine

Read:

- `README.md`
- `apps/ai_engine/README.md`
- `docs/ai_engine/README.md`

If AI engine behavior affects user-visible processing, summaries, matching, or recovery, also read:

- `docs/ux/overview.md`
- `docs/ux/states.md`
- relevant workflow/screen docs

### Full-stack

Read:

- `README.md`
- `apps/frontend/README.md`
- `apps/backend/README.md`
- `apps/ai_engine/README.md`
- `docker-compose.yml`
- `docs/architecture.md`
- relevant UX docs under `docs/ux/`

### UX / user-facing behavior

Read:

- `docs/product.md`
- `docs/design-principles.md`
- `docs/ux/overview.md`
- relevant workflow/screen/state/navigation docs under `docs/ux/`

### Architecture

Read:

- `docs/architecture.md`
- `docs/technical-decisions.md`
- relevant app README/code

### Production / deployment

Read:

- `docs/production.md`
- `docs/production-readiness.md`
- `docker-compose.prod.yml`
- `docs/architecture.md`

---

## 2. Documentation map

- `docs/spines.md`  
  **Multi-vertical strategy:** the three product spines, capability/tier matrix, sequencing, and per-spine next steps. Start here for product direction beyond today's aesthetics build.

- `docs/product.md`  
  Product purpose, users, MVP scope, and accepted product behavior.

- `docs/design-principles.md`  
  Non-negotiable product and UX principles.

- `docs/intelligence-layer.md`  
  Capture→intent **apply-semantics contract**: entity model, assignment timeline, out-of-context handling, and tiering. Other docs defer to it for "§5 apply semantics / §3 out-of-context / §2 entity model".

- `docs/ux/overview.md`  
  Compact entry point for current UX. Start here for user-facing tasks.

- `docs/ux/navigation.md`  
  Routes, screen hierarchy, entry points, and navigation paths.

- `docs/ux/states.md`  
  Shared loading, error, empty, success, offline, and permission states.

- `docs/ux/workflows/`  
  One compact file per major user workflow.

- `docs/ux/screens/`  
  One compact file per important screen.

- `docs/ux/redesign-session-context.md`  
  Spec for patient-context at point-of-determination (tier-aware) + the session↔timeline round-trip; Pro context window + its AI jobs (Job-4 backed).

- `docs/ux/redesign-pro-report.md`  
  Story-C design: polished synthesized-report rendering (clinical + curated patient share) + the recorded share/dose decisions.

- `docs/ux/redesign-smart-lists-recall.md`  
  Design + as-built for the Pro **smart lists** (AES-501) + **lot/product recall** (AES-502): the deterministic Lists tab in Clinical Memory, the trustworthy exact-match recall cohort + Q&A outreach handoff, and the AES-705 registry seam.

- `docs/architecture.md`  
  System architecture, modules, data flow, and boundaries.

- `docs/architecture/pipeline-versioning.md`  
  Content-addressed `report_version` store + user-state overlay — the versioning foundation behind capture undo / de-effecting and safety-reconcile.

- `docs/technical-decisions.md`  
  Important decisions future agents/developers need to know.

- `docs/business/ai-usage-limits.md`  
  Fair-use AI usage-limit system: measured per-job cost model, derived per-plan caps (monthly $ budget
  per seat + per-session soft cap), the metering/enforcement approach (`services/ai_usage/`), and the
  synthesis quiet-period debounce. Read before touching AI metering, limits, or the synthesis dispatch.

- `docs/ai_engine/README.md`  
  AI engine worker boundary, processing jobs, placeholder processors, and replacement path.

- `docs/ai_engine/capture-intelligence-design.md`  
  Approved build design for the Pro capture-intelligence wave (4 jobs, the synthesis+treatments A↔B contract, seams, decisions). Build keystone-first.

- `docs/backend/`  
  As-built backend: `README.md` (index), `design.md` (Postgres/MinIO/Celery/Alembic data + API design),
  `auth.md` (JWT auth, dev login, roles/tenants), `storage.md` (MinIO object storage),
  `aes-basic-api.md` and `aes-pro-qa-api.md` (aesthetics Basic + Pro Q&A API contracts).

- `docs/frontend/`  
  Frontend: `README.md` (index), `overview.md` (capture-first app structure + mobile testing),
  `auth-login.md` (login/persona flow), `i18n.md` (fa/en + RTL, chrome-vs-content axis, deferred scopes),
  `sync-outbox.md` (local-first outbox + cache policy).

- `docs/qa/`  
  Manual QA scripts: `aes-basic-smoke.md`, `aes-pro-smoke.md`, `aes-frontend-scenarios.md`,
  `aes-patient-pages-scenarios.md`.

- `docs/dev/`  
  Dev workflow: `worktree-stacks.md` (isolated per-worktree dev stacks), `screenshots.md`.

- `docs/production.md`  
  Production setup and operational notes.

- `docs/production-readiness.md`  
  Production gap list, ArvanCloud-tailored decisions, prioritized tasks, and the go-live checklist.

- `docs/production-alpha-tradeoffs.md`  
  The deliberate simplifications made for alpha testing (small single VPS, no monitoring) and how to undo each when scaling up — the migration checklist.

- `docs/monitoring.md`  
  Self-hosted observability overlay (Prometheus/Grafana/exporters + Uptime Kuma + GlitchTip) and what to watch.

The backend OpenAPI schema is the source of truth for exact API contracts. Do not create a large duplicate API contract document.

---

## 3. Documentation update rules

Update docs only when your change affects future understanding.

Update UX docs when changing:

- routes or navigation
- screens or visible behavior
- workflow steps
- loading/error/empty/success states
- offline or permission behavior
- backend behavior that affects UX

Update architecture/technical docs when changing:

- system boundaries
- major modules
- data flow
- infrastructure assumptions
- important technical decisions

Keep docs compact and modular. Do not duplicate details across files. Link to deeper docs when needed.

---

## 4. Implementation rules

- Keep changes focused on the requested task.
- Preserve existing behavior unless explicitly asked to change it.
- Prefer modifying existing modules/components over creating duplicates.
- Do not silently change product behavior.
- If code and docs conflict, mention the mismatch and make the smallest safe update.
- Keep code readable, typed, and maintainable.
- Validate with the relevant tests, linting, or type checks when available.
- **AI jobs are eval-gated.** Re-implementing or changing an existing AI job (transcription, image
  caption, report synthesis = treatments+aftercare+sections, patient memory, patient matching) MUST run
  the eval suite (`apps/ai_engine/eval/run_all.py`) and not regress it. A **new** AI job MUST ship its
  own eval suite — and you must **consult the user on its golden-set scenarios first** (don't design the
  eval set unilaterally). See `docs/ai_engine/eval-epic.md`.

---

## 5. Frontend rules

- Reuse existing components where reasonable.
- Keep presentational UI separate from API/business orchestration when practical.
- Keep screen behavior consistent with UX docs.
- **All new authenticated UI is bilingual (fa/en) + RTL-correct.** Route every user-facing chrome
  string through the `shared/i18n` `t()` seam — never hardcode UI text (the lint guard fails on it) —
  and check it under both languages. This is **chrome only**: clinical CONTENT (report prose, captions,
  treatment text, dictated aftercare) follows `reportLanguage`, never `t()`. (Public surfaces +
  authed app are both bilingual as of the i18n epic.)
- Do not over-complicate frontend code to work around an inefficient or awkward backend contract. If a frontend change would require significant client-side orchestration, duplicated business logic, excessive requests, heavy data reshaping, polling, or other work that could harm responsiveness, explicitly call out the backend/API change that would make the feature simpler and faster. If appropriate, either implement the backend change yourself within the requested scope or prepare a clear hand-off prompt for a backend engineer agent.
- Update UX docs if user-facing behavior changes.

---

## 6. Backend rules

- Keep route/controller layers thin.
- Put business logic in services or appropriate domain modules.
- Keep schemas/models typed and explicit.
- Return predictable error responses.
- Keep OpenAPI accurate.
- Update UX docs if backend behavior changes user-facing behavior.

---

## 7. Python conventions

- Use typing for function inputs and outputs.
- Use Google-style docstrings for public modules, classes, and functions unless they are small and self-explanatory.
- Add comments only when logic is non-obvious.

---

## 8. Running the app in a git worktree (isolated dev stack)

**Where to create worktrees:** under **`~/engram-worktrees/<branch-slug>`** — grouped in one place
and *outside* the repo, so the repo's Docker build context (`COPY . .`), `rg`/test discovery, and
dev-stack scripts never pick up a nested checkout. E.g.
`git worktree add ~/engram-worktrees/therapy -b p2/therapy-ux`. All worktrees share the main repo's
`.git` (same branches + objects), so a worktree's branch is merged from the primary checkout with a
normal `git merge <branch>` — the worktree's on-disk location is irrelevant to merging.

The dev-stack rule below applies **only if you are working inside a git worktree** (not the primary
checkout). Check with:

```sh
[ "$(git rev-parse --absolute-git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ] && echo "worktree"
```

If it prints `worktree`, then **do not run the root `docker compose up`** — it would
collide with other stacks on host ports and share the same database/object storage.
Instead launch an isolated stack:

```sh
scripts/dev-stack.sh up      # provision + start; prints this stack's app/API URLs
```

This uses shared Postgres + MinIO but gives your worktree its **own database** (cloned
from the canonical `engram` DB, so you inherit real data to test against) and its **own
bucket**, on **unique host ports**. Your branch's new Alembic migrations apply on top of
the cloned schema automatically. Stop it with `scripts/dev-stack.sh down` (add `--data`
to also drop this worktree's database + bucket). Full details:
`docs/dev/worktree-stacks.md`.

**When asked to clean up / finalize a worktree**, leave nothing stale behind:

1. Commit any outstanding work on the branch.
2. Get it merged into `main` — open/merge a PR, or merge from the primary checkout. You
   cannot check out `main` from inside the worktree (it is checked out elsewhere).
3. Run `scripts/dev-stack.sh clean` to remove this stack's containers, built images,
   volumes, database, and its MinIO bucket (including every media object it stored).
4. From the **primary checkout**, remove the worktree and delete the merged branch:
   `git worktree remove <path>` then `git branch -d <branch>`. The `clean` command prints
   these exact commands for the current worktree.

In the **primary checkout**, `scripts/dev-stack.sh up` runs the canonical `engram`
stack (the clone source); the plain root `docker compose up` also still works as a
self-contained, non-shared environment.
