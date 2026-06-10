# Isolated dev stacks per git worktree

When several agents/conversations each work in their own git worktree, each one needs a
running copy of the app it can test **independently** — without fighting over host ports
or sharing a database. This is handled by `scripts/dev-stack.sh`.

## Model

```text
                ┌─────────────────────── shared infra (project: notari-infra) ───────────────────────┐
                │  Postgres  (host :5442)              MinIO (host :9010 api / :9011 console)         │
                │   ├─ notari               (canonical / main dev data — the clone source)            │
                │   ├─ notari_<slugA>       bucket notari-captures            (canonical)              │
                │   └─ notari_<slugB>       bucket notari-captures-<slugA>    (mirror of canonical)    │
                └────────────────────────────────────────────────────────────────────────────────────┘
                        ▲ backend only                         ▲ backend only
   ┌── main checkout ───┴──┐   ┌── worktree A ────┴──┐   ┌── worktree B ───────────┐
   │ backend  :8010        │   │ backend  :81xx       │   │ backend  :81yy          │
   │ frontend :5183        │   │ frontend :52xx       │   │ frontend :53yy          │
   │ ai-engine + redis     │   │ ai-engine + redis    │   │ ai-engine + redis       │
   │ db = notari           │   │ db = notari_<slugA>  │   │ db = notari_<slugB>     │
   └───────────────────────┘   └──────────────────────┘   └─────────────────────────┘
```

- **Shared (one instance, heavy/stateful):** Postgres + MinIO. Defined in
  `docker-compose.shared-infra.yml`, run as the `notari-infra` Compose project.
- **Per stack (cheap / under development):** backend, ai-engine, frontend, and a local
  redis. Defined in `docker-compose.app.yml`.
- **Why only the backend joins the shared network:** the ai-engine never touches
  Postgres/MinIO directly — it reaches everything through the backend's internal HTTP
  API. So nothing about service-to-service naming (`backend`, `redis`) collides between
  stacks; each stack keeps its own private default network.

### What "isolated" means here

| Concern | How it's isolated |
| --- | --- |
| Compose network, containers, redis | Per-stack Compose project name (`notari_<slug>`) |
| Database | Per-stack DB `notari_<slug>`, **cloned from `notari`** on first `up` |
| Object storage | Per-stack bucket `notari-captures-<slug>`, mirrored from the canonical bucket |
| Host ports | `FRONTEND_PORT` / `BACKEND_PORT` auto-picked free and pinned in the worktree `.env` |
| Shared Postgres/MinIO host ports | Fixed (5442 / 9010 / 9011) — one shared instance, so no clash |

## Inheriting data from the main database

On the first `up` for a worktree, the stack's database is created by cloning the
canonical `notari` database (`pg_dump … | psql`), including its `alembic_version`. So you
start with the same accounts and data you have in main, then your branch's new migrations
apply on top via the backend's `alembic upgrade head`. Capture media is mirrored from the
canonical bucket so inherited captures actually render.

Re-seed at any time:

```sh
scripts/dev-stack.sh refresh   # drop + re-clone this worktree's DB and media from main, restart
```

> The canonical `notari` data lives in shared infra, independent of any worktree's
> lifecycle — tearing a worktree stack down (even with `--data`) never touches it. A git
> **merge** moves code only; it never moves a stack's rows. After merging a branch, run
> the main stack and its `notari` data is exactly as you left it, with the merged
> migrations applied.

## Commands

Run from inside the checkout you want to launch (main repo or a worktree):

```sh
scripts/dev-stack.sh up          # provision shared infra + DB/bucket, start this stack, print URLs
scripts/dev-stack.sh status      # list running stacks + this stack's URLs
scripts/dev-stack.sh down        # stop this stack's containers (keep its database + bucket)
scripts/dev-stack.sh down --data # also DROP this worktree's database + bucket
scripts/dev-stack.sh clean       # full teardown: containers + built images + volumes + DB + bucket (worktree only)
scripts/dev-stack.sh refresh     # re-clone DB + re-mirror media from main, restart (worktree only)
scripts/dev-stack.sh infra-up    # start shared Postgres + MinIO only
scripts/dev-stack.sh infra-down  # stop shared infra (volumes/data preserved)
```

The script may be invoked by absolute path from anywhere
(`"/Users/soroush/notari/scripts/dev-stack.sh" up`); it finds the main
repo from its own location and the target checkout from your current directory. The only
file it writes into the worktree is `.env`.

## Cleanup / finalizing a worktree

When a worktree's work is done, remove everything it created so no stale
containers/images/branches accumulate:

```sh
# 1. In the worktree: commit outstanding work.
git add -A && git commit -m "…"

# 2. Get the branch merged into main (PR, or merge from the primary checkout —
#    you cannot check out main from inside the worktree).

# 3. In the worktree: tear down all docker artifacts for this stack.
scripts/dev-stack.sh clean       # containers + built images + volumes + database
                                 # + MinIO bucket (and every object in it)

# 4. From the PRIMARY checkout: drop the worktree and its merged branch.
#    (`clean` prints these exact lines for the current worktree.)
git worktree remove <worktree-path>
git branch -d <branch>           # -d refuses unless merged; -D only to discard unmerged work
```

What `clean` removes, so nothing is left orphaned:

- Containers + the stack's local volumes (redis data, node_modules).
- The built `backend` / `ai-engine` / `frontend` images for this stack.
- The Postgres database `notari_<slug>`.
- The MinIO bucket `notari-captures-<slug>` **and all media objects in it**
  (`mc rb --force`) — both the initial mirror and anything the stack uploaded.

The local `./captures` directory (gitignored) is removed with the worktree in step 4.
`clean` only operates on worktree stacks — it refuses to touch the canonical `notari`
database/bucket or the main stack, and the shared `redis` / Postgres / MinIO base images
are pulled (not built), so they are left intact.

## One-time: seeding shared `notari` with your existing data

The shared Postgres starts empty. The legacy all-in-one root stack
(`docker compose up`) and the shared infra **cannot run at the same time** — they bind
the same host ports (5442 / 9010 / 9011). So migrate your existing data in sequence:

```sh
# 1. With your current root stack running, dump the main DB to a file:
docker compose exec -T postgres pg_dump -U notari -d notari --no-owner --no-privileges > /tmp/notari-main.sql

# 2. Stop the legacy root stack (frees the shared ports):
docker compose down

# 3. Start shared infra and restore into the canonical `notari` DB:
scripts/dev-stack.sh infra-up
docker compose -p notari-infra -f docker-compose.shared-infra.yml exec -T postgres \
  psql -q -U notari -d notari < /tmp/notari-main.sql
```

After this, `notari` in shared infra is the canonical source every new stack clones from,
and you launch the main app with `scripts/dev-stack.sh up` instead of the root
`docker compose up`. (Optional: mirror existing capture media the same way with
`mc mirror` between the two MinIO instances, run sequentially.)

## Adding stacks / resource notes

- Each stack is 4 containers (backend, ai-engine, frontend, redis) plus the one shared
  Postgres + MinIO. Far lighter than a full all-in-one stack per worktree.
- Slugs are derived from the branch name; ports are pinned per worktree in `.env`, so a
  stack keeps the same ports across restarts.
- If a worktree is specifically changing storage/MinIO behavior, point it at its own
  MinIO instead of the shared one (override `BACKEND_OBJECT_STORAGE_*` in its `.env`) so
  it can't corrupt shared objects.
