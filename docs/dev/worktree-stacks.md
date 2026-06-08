# Isolated dev stacks per git worktree

When several agents/conversations each work in their own git worktree, each one needs a
running copy of the app it can test **independently** — without fighting over host ports
or sharing a database. This is handled by `scripts/dev-stack.sh`.

## Model

```text
                ┌─────────────────────── shared infra (project: aesmem-infra) ───────────────────────┐
                │  Postgres  (host :5442)              MinIO (host :9010 api / :9011 console)         │
                │   ├─ aesmem               (canonical / main dev data — the clone source)            │
                │   ├─ aesmem_<slugA>       bucket aesmem-captures            (canonical)              │
                │   └─ aesmem_<slugB>       bucket aesmem-captures-<slugA>    (mirror of canonical)    │
                └────────────────────────────────────────────────────────────────────────────────────┘
                        ▲ backend only                         ▲ backend only
   ┌── main checkout ───┴──┐   ┌── worktree A ────┴──┐   ┌── worktree B ───────────┐
   │ backend  :8010        │   │ backend  :81xx       │   │ backend  :81yy          │
   │ frontend :5183        │   │ frontend :52xx       │   │ frontend :53yy          │
   │ ai-engine + redis     │   │ ai-engine + redis    │   │ ai-engine + redis       │
   │ db = aesmem           │   │ db = aesmem_<slugA>  │   │ db = aesmem_<slugB>     │
   └───────────────────────┘   └──────────────────────┘   └─────────────────────────┘
```

- **Shared (one instance, heavy/stateful):** Postgres + MinIO. Defined in
  `docker-compose.shared-infra.yml`, run as the `aesmem-infra` Compose project.
- **Per stack (cheap / under development):** backend, ai-engine, frontend, and a local
  redis. Defined in `docker-compose.app.yml`.
- **Why only the backend joins the shared network:** the ai-engine never touches
  Postgres/MinIO directly — it reaches everything through the backend's internal HTTP
  API. So nothing about service-to-service naming (`backend`, `redis`) collides between
  stacks; each stack keeps its own private default network.

### What "isolated" means here

| Concern | How it's isolated |
| --- | --- |
| Compose network, containers, redis | Per-stack Compose project name (`aesmem_<slug>`) |
| Database | Per-stack DB `aesmem_<slug>`, **cloned from `aesmem`** on first `up` |
| Object storage | Per-stack bucket `aesmem-captures-<slug>`, mirrored from the canonical bucket |
| Host ports | `FRONTEND_PORT` / `BACKEND_PORT` auto-picked free and pinned in the worktree `.env` |
| Shared Postgres/MinIO host ports | Fixed (5442 / 9010 / 9011) — one shared instance, so no clash |

## Inheriting data from the main database

On the first `up` for a worktree, the stack's database is created by cloning the
canonical `aesmem` database (`pg_dump … | psql`), including its `alembic_version`. So you
start with the same accounts and data you have in main, then your branch's new migrations
apply on top via the backend's `alembic upgrade head`. Capture media is mirrored from the
canonical bucket so inherited captures actually render.

Re-seed at any time:

```sh
scripts/dev-stack.sh refresh   # drop + re-clone this worktree's DB and media from main, restart
```

> The canonical `aesmem` data lives in shared infra, independent of any worktree's
> lifecycle — tearing a worktree stack down (even with `--data`) never touches it. A git
> **merge** moves code only; it never moves a stack's rows. After merging a branch, run
> the main stack and its `aesmem` data is exactly as you left it, with the merged
> migrations applied.

## Commands

Run from inside the checkout you want to launch (main repo or a worktree):

```sh
scripts/dev-stack.sh up          # provision shared infra + DB/bucket, start this stack, print URLs
scripts/dev-stack.sh status      # list running stacks + this stack's URLs
scripts/dev-stack.sh down        # stop this stack's containers (keep its database + bucket)
scripts/dev-stack.sh down --data # also DROP this worktree's database + bucket
scripts/dev-stack.sh refresh     # re-clone DB + re-mirror media from main, restart (worktree only)
scripts/dev-stack.sh infra-up    # start shared Postgres + MinIO only
scripts/dev-stack.sh infra-down  # stop shared infra (volumes/data preserved)
```

The script may be invoked by absolute path from anywhere
(`"/Users/soroush/AIMed Project Base/AesMem/scripts/dev-stack.sh" up`); it finds the main
repo from its own location and the target checkout from your current directory. The only
file it writes into the worktree is `.env`.

## One-time: seeding shared `aesmem` with your existing data

The shared Postgres starts empty. The legacy all-in-one root stack
(`docker compose up`) and the shared infra **cannot run at the same time** — they bind
the same host ports (5442 / 9010 / 9011). So migrate your existing data in sequence:

```sh
# 1. With your current root stack running, dump the main DB to a file:
docker compose exec -T postgres pg_dump -U aesmem -d aesmem --no-owner --no-privileges > /tmp/aesmem-main.sql

# 2. Stop the legacy root stack (frees the shared ports):
docker compose down

# 3. Start shared infra and restore into the canonical `aesmem` DB:
scripts/dev-stack.sh infra-up
docker compose -p aesmem-infra -f docker-compose.shared-infra.yml exec -T postgres \
  psql -q -U aesmem -d aesmem < /tmp/aesmem-main.sql
```

After this, `aesmem` in shared infra is the canonical source every new stack clones from,
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
