# work-docs — process workspace

Temporary home for **process docs**: epics, stories, design explorations, build plans, migration
checklists, research briefs. Everything under `docs/` is **system-state** — it describes what
*is*, in the present tense, and must always match the code.

## Lifecycle

1. **Create** a doc here when starting a design/epic/plan. Name it after the work, not the doc type
   (e.g. `therapy-vertical.md`, not `epic-3.md`).
2. **Build.** Track status, decisions, and open questions here freely.
3. **Fold** the durable essence (contracts, as-built behavior, decisions worth keeping) into the
   system-state docs (`docs/ux/screens/…`, `docs/architecture.md`, `docs/technical-decisions/`, …).
4. **Delete** the doc. Rewire or remove any links to it first.

## Rules

- **System-state docs must never link into `work-docs/`.** If a system-state doc needs to reference
  something here, that content is durable — fold it out first. (This is the tripwire that forces
  step 3 before step 4.)
- A doc here may describe future/unbuilt state; a system-state doc may not. No "Status: not built"
  or "superseded by…" banners outside this directory — rewrite the system-state doc instead.
- Each doc should open with one line naming its **fold destination(s)** — where the essence goes
  when the work ships.
- Anything in this directory is deletable once its work is merged; agents should prune finished
  items as part of closing out an epic.
