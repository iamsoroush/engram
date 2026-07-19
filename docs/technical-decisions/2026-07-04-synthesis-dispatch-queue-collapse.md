# Synthesis Dispatch — Queue-Collapse, No Debounce (2026-07-04)

**Supersedes the quiet-period synthesis debounce.** An earlier design coalesced a visit's per-capture
synthesis runs with a time-window **debounce** (`synthesis_debounce_seconds`, default 0 = off, driven
by a trailing Celery-beat sweep). That setting, `session_synthesis_within_debounce`, and
`sweep_debounced_session_synthesis` are **removed**. Report synthesis (`session_organize`) is the
dominant AI cost (per-capture re-synthesis measured ~8.8× a coalesced run —
[business/ai-usage-limits.md](../business/ai-usage-limits.md)); it is now cost-controlled with **no timer
and no added latency**:

- **Queue-collapse dispatch.** Single-flight per session + at most one pending job. The first capture
  synthesizes immediately; a trigger while a job is *queued* is a no-op (the queued job reads the full
  current capture set at `/start`), and a trigger while one is *running* yields exactly one collapsed
  follow-up (dispatched by the running job's completion handler). A **failed-but-retryable** job also
  counts as in-flight (`session_has_active_report_job`), so a capture arriving during the failure window
  merges into that job's recovery-beat retry instead of spawning a second job; a *terminal* failure does
  not block. A burst of N captures costs ≤ 2 runs instead of N. `force=True` (content edits / manual
  regenerate) keeps its meaning.
- **Cache-hit before dispatch.** Every settle first checks the content-addressed
  `session_report_versions` store for the current capture-set hash and **restores** deterministically
  instead of re-synthesizing (edit-then-revert, mark-relevant toggles, re-adds). Out-of-context
  membership is now part of the capture-set hash (pipeline-versioning **D1**), so a mark-relevant
  toggle is a correct hit/miss; the user-state overlay is re-applied on restore (ground-truth invariant).
- The debounce sweep is **repurposed** as `sweep_pending_session_synthesis` — a recovery-beat *catch-up*
  safety net (re-triggers a session left with an uncontributed capture and no active job), **not** a
  timer.

Worker and eval golden-set are unaffected (this changes *when/whether* synthesis runs, never its
inputs/outputs). See [backend/processing.md](../backend/processing.md) "Pro report synthesis".
