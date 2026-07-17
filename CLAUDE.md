# CLAUDE.md

This repository is developed with AI coding agents.

**Naming:** the platform and product share a single brand — **Engram** — used everywhere: repo, services, infra, API, and all customer-facing surfaces. Engram is capture-first clinical memory, currently for aesthetics clinics (therapy and dermatology are the next verticals). Production might be live at `engram.ir`.

Use this file as the starting guide. Do not read the whole repository blindly. Start from the relevant README/docs, then inspect only the files needed for the task. **§2 below is the single documentation index** — other indexes (`docs/README.md`, app READMEs) defer to it.

---

## 1. First step by task type

### Every task — read these first

Regardless of task type, read these two before anything else. They are the shared mental model the
rest of the docs assume, and both are short:

- `docs/product.md` — what Engram is: purpose, personas, verticals × tiers × surfaces, the core
  loop, accepted behaviors.
- `docs/design-principles.md` — the non-negotiable product/UX principles; a change that is locally
  correct but violates one of these is wrong.

Then continue with the task-type lists below.

### Frontend

Read:

- `apps/frontend/README.md`
- `docs/frontend/README.md`

If the task changes visible behavior, also read:

- `docs/ux/overview.md`
- relevant files under `docs/ux/workflows/` or `docs/ux/screens/`

### Backend

Read:

- `apps/backend/README.md`
- `docs/backend/README.md`

If backend behavior affects users, also read:

- `docs/ux/overview.md`
- relevant workflow/screen docs

### AI Engine

Read:

- `apps/ai_engine/README.md`
- `docs/ai_engine/README.md` (indexes `processing.md` — the as-built jobs doc — and `evals.md`)

If AI engine behavior affects user-visible processing, summaries, matching, or recovery, also read:

- `docs/ux/overview.md`
- `docs/ux/states.md`
- relevant workflow/screen docs

### Full-stack

Read:

- `apps/frontend/README.md`
- `apps/backend/README.md`
- `apps/ai_engine/README.md`
- `docker-compose.yml`
- `docs/architecture.md`
- relevant UX docs under `docs/ux/`

### UX / user-facing behavior

Read (on top of the every-task pair above):

- `docs/ux/foundation.md` (tier/persona/boundary decisions — read before designing any surface)
- `docs/ux/overview.md`
- `docs/intelligence-layer.md` (if the work touches capture→intent/apply behavior)
- relevant workflow/screen/state/navigation docs under `docs/ux/`

### Architecture

Read:

- `docs/architecture.md`
- `docs/technical-decisions.md`
- relevant app README/code

### Production / deployment

Read:

- `docs/production.md`
- `docs/production-alpha-tradeoffs.md`
- `docker-compose.prod.yml`
- `docs/architecture.md`

---

## 2. Documentation map

Product & strategy:

- `docs/product.md`  
  Top-of-funnel current-product doc: purpose, personas, verticals × tiers × surfaces, the core loop, accepted behaviors.

- `docs/spines.md`  
  **Multi-vertical strategy:** the three product spines, the capability/tier matrix (canonical for what each tier contains — `services/capabilities.py` implements it), sequencing, and per-spine frontier.

- `docs/design-principles.md`  
  Non-negotiable product and UX principles (Spine-A scope).

- `docs/intelligence-layer.md`  
  Capture→intent **apply-semantics contract**: entity model, assignment timeline, out-of-context handling. Other docs defer to it for "§5 apply semantics / §3 out-of-context / §2 entity model". Tier contents defer to `spines.md` §3.

UX (system-state):

- `docs/ux/overview.md`  
  Compact entry point for current UX. Start here for user-facing tasks.

- `docs/ux/foundation.md`  
  The tier/persona/boundary design-foundation record every surface design builds on.

- `docs/ux/navigation.md`  
  Routes, screen hierarchy, entry points, and navigation paths.

- `docs/ux/states.md`  
  Shared loading, error, empty, success, offline, permission, and AI-usage-limit states.

- `docs/ux/workflows/`  
  One compact file per major user workflow.

- `docs/ux/screens/`  
  One compact file per important screen (incl. `capture.md` — the primary surface, with the partial-match matrix and undo UX — `patients.md` with the Pro Lists tab + worklist, `qa-inbox.md`, `patient-surface.md` for the public `/share` + `/qa` pages, `insights.md`, `finder.md` — the app-wide unified-finder overlay that replaced the old `/#search` screen).

- `docs/ux/aesthetics-stories.md`  
  The AES-### story registry (IDs, status, decisions) that specs, QA scripts, and code comments cite.

Architecture & backend:

- `docs/architecture.md`  
  System architecture, modules, data flow, and boundaries.

- `docs/architecture/pipeline-versioning.md`  
  Content-addressed `report_version` store + user-state overlay — the versioning foundation behind capture undo / de-effecting and safety-reconcile (with built-vs-pending status).

- `docs/technical-decisions.md`  
  Dated decision log future agents/developers must respect (with superseding notes where reversed).

- `docs/backend/`  
  As-built backend: `README.md` (index), `data-model.md` (Postgres data model + state semantics),
  `processing.md` (backend-side AI-job orchestration: dispatch, gating, debounce, recovery),
  `auth.md` (JWT auth, dev login, roles/tenants), `storage.md` (MinIO object storage),
  `aes-basic-api.md` and `aes-pro-qa-api.md` (aesthetics Basic + Pro Q&A API contracts),
  `insights-feedback.md` (Insights + AI-feedback endpoints).

AI engine:

- `docs/ai_engine/README.md`  
  Worker boundary, the vertical-agnostic prompt rule, and the index for the two docs below.

- `docs/ai_engine/processing.md`  
  THE as-built AI-jobs doc: all worker jobs (transcription+intents, caption, note passthrough, report synthesis incl. the A↔B contract + safety-reconcile, patient memory, Q&A draft/revise), fallbacks, recovery, live model config.

- `docs/ai_engine/evals.md`  
  How the eval system works: scoring tiers, expectations format, fixtures, harvest loop, coverage table, CI status.

Frontend:

- `docs/frontend/`  
  `README.md` (index), `overview.md` (capture-first app structure + mobile testing),
  `auth-login.md` (login/persona flow), `i18n.md` (fa/en + RTL, chrome-vs-content axis, deferred scopes),
  `sync-outbox.md` (local-first outbox + cache policy).

Business:

- `docs/business/ai-usage-limits.md`  
  Fair-use AI usage-limit system: measured per-job cost model, derived per-plan caps, the metering/enforcement approach (`services/ai_usage/`), and the synthesis quiet-period debounce. Read before touching AI metering, limits, or the synthesis dispatch.

- `docs/business/compute-cost-model.md`  
  Infra COGS, storage compounding, and minimum-profitable-price methodology (its AI-COGS section is superseded by `ai-usage-limits.md` — see its banner).

- `docs/business/pricing.md`  
  The current price anchors and how they reconcile; canonical decision pending discovery.

- `docs/business/interview-kit.md`  
  Customer-discovery/WTP interview kit for the current Tehran wave (operational GTM artifact; prune after the wave's readout).

QA & dev workflow:

- `docs/qa/`  
  Manual QA scripts: `aes-basic-smoke.md` (incl. against-production variant), `aes-pro-smoke.md`, `aes-frontend-scenarios.md` (exhaustive Basic), `aes-patient-pages-scenarios.md` (public share pages).

- `docs/dev/`  
  Dev workflow: `worktree-stacks.md` (isolated per-worktree dev stacks), `screenshots.md`.

Production & operations:

- `docs/production.md`  
  Current live deployment (engram.ir), stack shape incl. Caddy/TLS, env vars, deploy/rollback paths (incl. rsync `SKIP_GIT_PULL`), backups/restore, CI overview.

- `docs/production-alpha-tradeoffs.md`  
  The deliberate-debt register: alpha simplifications and how to undo each when scaling up.

- `docs/monitoring.md`  
  Self-hosted observability overlay (built, not yet deployed — the doc states how to enable) and what to watch.

Process workspace:

- `docs/work/`  
  **Temporary process docs** (epics, stories, design explorations, plans) — see `docs/work/README.md` for the lifecycle. Everything else under `docs/` is system-state.

The backend OpenAPI schema is the source of truth for exact API contracts. Do not create a large duplicate API contract document.

---

## 3. Documentation rules

**Two classes of docs.** Everything under `docs/` except `docs/work/` is **system-state**: it
describes what IS, in the present tense, and must match the code at all times. **Process docs**
(epics, stories, design explorations, build plans, migration checklists) live in `docs/work/` and
follow its lifecycle: create → build → fold durable essence into system-state docs → delete.

- A system-state doc never contains "Status: not built", phased plans, or "superseded by…" banners.
  If it goes stale, rewrite it — don't annotate it.
- System-state docs never link into `docs/work/`. If one needs to, that content is durable — fold it
  out first.
- When an epic/story finishes, delete its process doc after folding; rewire every inbound link
  (zero broken links).
- **Volatile enumerations point at code**, not prose copies: feature lists → `src/features/`, job
  types → `AiJobType` in `app/models.py`, env vars → the app's `config.py` / `.env.prod.example`.
  Hand-maintained copies of these lists are how docs rot.
- This file's §2 is the **only** doc index. Don't build parallel doc maps.

Update docs only when your change affects future understanding.

Update UX docs when changing: routes or navigation; screens or visible behavior; workflow steps;
loading/error/empty/success states; offline or permission behavior; backend behavior that affects UX.

Update architecture/technical docs when changing: system boundaries; major modules; data flow;
infrastructure assumptions; important technical decisions.

Keep docs compact and modular. Do not duplicate details across files — every fact has exactly one
home; link to it. Contracts (`intelligence-layer.md`, `spines.md` §3) are referenced, not restated.

**Close the loop — before you declare a task done**, walk this checklist (it is part of the task,
not optional cleanup):

1. **Behavior changed?** Routes/screens/states/workflows → update the matching `docs/ux/` doc.
   Backend behavior that users can see counts.
2. **Boundaries/data changed?** New module, data flow, table/enum, job type, infra assumption →
   `docs/architecture.md`, `docs/backend/data-model.md` / `processing.md`, or the app doc that owns it.
3. **Decision made or reversed?** Add a dated entry to `docs/technical-decisions.md`; if it reverses
   an earlier entry, add a superseding note on the old one (never silently contradict it).
4. **AI job touched?** Run the eval suite; new job → new eval + update `docs/ai_engine/evals.md`'s
   coverage table (see §4).
5. **New story/scope?** Register the AES-### (or vertical equivalent) in the story registry.
6. **Doc added, moved, or deleted?** Update the §2 map above (the single index) and rewire every
   inbound link. Epic/story finished → fold + delete its `docs/work/` doc.
7. **Verify zero broken links:** run `python3 scripts/check-doc-links.py` (CI runs it too — it fails
   on dangling links and on system-state docs linking into `docs/work/`).
8. **Reusable learning, or a skill that misled you?** Propose the skill change to the user and
   apply it once confirmed (§9).

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
  caption, report synthesis = treatments+aftercare+sections+safety, patient memory, patient matching,
  Q&A draft/revise) MUST run the eval suite (`apps/ai_engine/eval/run_all.py`) and not regress it. A
  **new** AI job MUST ship its own eval suite — and you must **consult the user on its golden-set
  scenarios first** (don't design the eval set unilaterally). `qa_draft`/`qa_revise` are eval-gated too
  (`qa_draft_eval.py` / `qa_revise_eval.py`, registered in `run_all.py`; the voice-edit fixtures
  `r01–r10` are still owner-supplied). See `docs/ai_engine/evals.md`.

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

---

## 9. Skills — self-maintained reusable procedures

Skills are proven, tested procedures that load automatically into every agent. They live in
`.claude/skills/<name>/SKILL.md`; `.agents/skills` is a symlink to `.claude/skills` (Codex reads
skills from there) — **edit only `.claude/skills/`** and both stay in sync. For format, authoring,
and improving skills, use the bundled `skill-creator` skill.

**All skill writes are user-gated.** Before creating, editing, or deleting any skill, present the
proposed change to the user — what you want to capture or fix, why, and the draft/diff — and apply
it only after they confirm. Never modify `.claude/skills/` silently.

Maintaining skills is part of every task, not optional cleanup:

- **Capture.** When you solve something through real trial-and-error that will recur — a
  debugging recipe, a migration procedure, a verification flow, a repo-specific workflow — fold
  it into a skill: the steps that worked AND the dead ends / common mistakes. Don't capture
  one-off or trivial knowledge, and never capture an approach you haven't actually validated in
  this repo.
- **Update.** When a task reveals an existing skill is incomplete, stale, or wrong, fix the
  skill within the same task.
- **Self-reflect on failure.** If you went off track while following a skill, diagnose why
  before finishing: was the skill wrong, ambiguous, or missing a precondition — or did you
  misapply it? Update the skill so the next agent doesn't repeat the mistake. A skill that
  misled an agent and was left unchanged is a bug.
- **Skills hold procedure, docs hold facts.** How to do a recurring task well → skill. What the
  system IS (architecture, contracts, data model) → `docs/` (§2–§3). Skills link to docs, never
  restate them.
