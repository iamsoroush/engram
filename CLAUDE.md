# CLAUDE.md

This repository is developed with AI coding agents.

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
- `docker-compose.prod.yml`
- `docs/architecture.md`

---

## 2. Documentation map

- `docs/product.md`  
  Product purpose, users, MVP scope, and accepted product behavior.

- `docs/design-principles.md`  
  Non-negotiable product and UX principles.

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

- `docs/architecture.md`  
  System architecture, modules, data flow, and boundaries.

- `docs/technical-decisions.md`  
  Important decisions future agents/developers need to know.

- `docs/ai_engine/README.md`  
  AI engine worker boundary, processing jobs, placeholder processors, and replacement path.

- `docs/production.md`  
  Production setup and operational notes.

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

---

## 5. Frontend rules

- Reuse existing components where reasonable.
- Keep presentational UI separate from API/business orchestration when practical.
- Keep screen behavior consistent with UX docs.
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

This rule applies **only if you are working inside a git worktree** (not the primary
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
from the canonical `notari` DB, so you inherit real data to test against) and its **own
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

In the **primary checkout**, `scripts/dev-stack.sh up` runs the canonical `notari`
stack (the clone source); the plain root `docker compose up` also still works as a
self-contained, non-shared environment.
