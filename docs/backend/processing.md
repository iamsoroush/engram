# Backend Processing (AI-job orchestration)

The backend side of the AI pipeline: it creates durable job rows, decides *whether* and *when*
each job is dispatched to Celery, applies completed outputs, and recovers stalled work. Execution
(prompts, gateway calls, model choice) lives in the worker — see
[docs/ai_engine/processing.md](../ai_engine/processing.md); the two communicate only via named
Celery tasks and the protected `/internal/ai/...` HTTP endpoints. Job rows and types:
[data-model.md](data-model.md) "AI Jobs".

## Orchestration layer — `services/ai_jobs/`

Split by concern (all public names re-exported from the package root):

- `orchestration.py` — job creation + the **dispatch chokepoints** (`dispatch_capture_processing_job`,
  `dispatch_session_processing_job`, `dispatch_patient_memory_job`). `TASK_NAME_BY_JOB_TYPE` maps
  each `AiJobType` to its `ai_engine.*` Celery task name — the one registry to extend for a new
  job type. Patient-memory dispatch triggers and Celery priorities also live here.
- `reports.py` — the deterministic live-report rebuild + Pro synthesis dispatch gating and debounce
  (below).
- `recovery.py` — durable retry primitives (`schedule_retry`, bounded exponential backoff,
  `retry_reason` classification) and the recovery loops.
- `worker.py` — the `/internal/ai/jobs/{id}/start|progress|complete|retry|fail` lifecycle handlers:
  payload assembly for the worker, applying completed outputs (capture text, synthesis artifacts,
  AI patient assignment), and usage metering on completion.
- `base.py` / `config.py` / `context.py` / `intents.py` — job serialization, tenant config getters,
  worker-context builders, and assignment-intent resolution.

**Capture-chain ordering:** a session's capture jobs process in capture order (the assignment gate
depends on cumulative session state). Only the *chain head* — the earliest unfinished capture job
in the session — is dispatched (`is_capture_chain_head`); each completion dispatches the next
(`dispatch_next_session_capture`) and re-queues retryable failed siblings. Session-level and
patient-scoped jobs are never chain-gated.

**Celery priorities:** interactive work rides the default priority 0; patient-memory refreshes are
tiered (0 = patient just opened, 3 = added to line-up, 6 = background sweep) so a memory backlog
never delays capture processing. The worker consumes the base queue before the demoted tiers.

## Tier gating — `services/capabilities.py`

Features gate on **capabilities**, never on `tier` directly: each `(vertical, tier)` resolves to a
capability set (see [docs/spines.md](../spines.md) §3). Aesthetics **Basic resolves to zero AI
capabilities**: a Basic capture upload creates *no* AI job and no `processing` state — the capture
is saved deterministically and the report is rebuilt synchronously in the same request
(`tenant_processes_captures_with_ai`). Therapy is a single plan with the full set. The synthesis
and patient-memory dispatchers each self-gate on their capability (`LIVE_REPORT_SYNTHESIS`,
`CROSS_VISIT_SYNTHESIS`).

## Deterministic live-report rebuild — `regenerate_session_report`

The report floor is **not** an AI job. Whenever a session's capture chain is idle
(`regenerate_session_report_if_idle`), the backend rebuilds `report_model` synchronously as a pure
function of the session's processed, in-context captures — no LLM, always current:

- **Pro** (`LIVE_REPORT_SYNTHESIS` capability): blocks grouped by type (Audio notes / Written
  notes / Photos).
- **Basic**: a single chronological section.
- **Therapy**: branches to its own narrative synthesis path (`services/therapy_reporting.py`).

The rebuild never clobbers a current LLM synthesis: if a synthesized report exists for the exact
current content signature (`session_report_content_signature`), the deterministic baseline stays
the floor and is left alone. After the rebuild the session settles to `needs_review` /
`unassigned` and completeness is derived (no manual verify).

## Pro report synthesis — queue-collapse dispatch + cache-hit-before-dispatch

The `session_organize` job is the Pro single-pass LLM report synthesis (prose + treatments +
safety flags + aftercare — the dominant AI cost). It runs *after* the deterministic baseline as a
quiet refinement (`mark_processing=False` — the visible report never flashes to `processing`).
`maybe_dispatch_session_synthesis` is the single dispatch chokepoint; it dispatches only when **all**
of these hold:

1. `BACKEND_REPORT_SYNTHESIS_ENABLED` is on (the backend-visible proxy for "a synthesis gateway is
   configured"; default off, so gateway-less environments dispatch zero synthesis),
2. the tenant has the `LIVE_REPORT_SYNTHESIS` capability,
3. the vertical is not therapy (it has its own path),
4. no capture jobs are pending and no report job is already **in flight** (`session_has_active_report_job`
   — queued, running, **or failed-but-pending-retry**),
5. some reportable capture is not yet folded in (`report_contribution != added`) — or the caller
   forces it after a content-changing edit/delete.

**Queue-collapse dispatch (no timer, no debounce).** The first capture synthesizes **immediately** —
per-capture responsiveness is intact — while redundant *queued* work is eliminated by two invariants:

- **Single-flight + at most one pending job per session.** Guard 4 (`session_has_active_report_job`)
  makes a trigger while a job is merely *queued* a no-op: that queued job reads the **full current
  capture set when it starts** (`worker_job_payload` is built at `/start`, not at enqueue), so captures
  that land while it waits are absorbed for free. A trigger while a job is *running* is likewise a no-op
  here; the running job's completion handler re-invokes `maybe_dispatch_session_synthesis`, which
  dispatches the single pending follow-up covering everything the running job didn't see. A **failed**
  synthesis job that is still retryable also counts as in-flight: the recovery beat re-dispatches that
  same job (re-reading the full current set), so a capture landing during the failure window merges
  into that retry rather than spawning a second job. A *terminal* failure (`retryable=False`) does not
  block — it will never retry.
- Result: a burst of N captures costs **≤ 2 runs** (the in-flight one + one collapsed follow-up)
  instead of N; a single-capture visit adds zero latency and zero extra cost. `force=True` (content
  edits / manual regenerate) keeps its meaning — it re-synthesizes past the all-contributed guard.

**Cache-hit before dispatch.** Before creating a synthesis job, `restore_cached_session_synthesis`
checks the content-addressed `session_report_versions` store for the **current capture-set hash**; a
hit **restores** that exact synthesized artifact deterministically (no LLM) and skips the dispatch —
covering edit-then-revert, mark-relevant toggles, and re-add-the-same. Out-of-context membership is
part of the capture-set hash (D1), so a mark-relevant toggle is a distinct set (correct hit/miss). On
restore the immutable AI artifact is applied, then the **user-state overlay** on top: the restored
source captures flip to `added`, the session's kept safety flags (detected − `rejected_safety_flags`)
are re-projected onto the patient and the reconcile decisions re-applied — exactly as a fresh
synthesis completion would (ground-truth invariant). See
[pipeline-versioning](../architecture/pipeline-versioning.md) and
[docs/business/ai-usage-limits.md](../business/ai-usage-limits.md).

On completion the worker-side output is applied, per-capture `report_contribution` flips to
`added`, patient safety flags are re-synced (with the safety-reconcile decisions), and the result
is snapshotted as a content-addressed `session_report_versions` row.

## Fair-use deferral (parking) — `services/ai_usage/`

Every dispatch chokepoint consults one gate, `should_defer_dispatch`: when the clinic's real
metered spend has reached its monthly budget (or a single session exceeds the per-session soft
cap), the job is **parked** — kept `queued`, marked `ai_usage_deferred`, never sent to Celery.
Capture itself is never gated; only background enrichment waits. Parked jobs resume automatically
on the recovery beat once the budget frees (new period / plan change). Metering writes real
gateway usage into `ai_usage_counters` on job completion. Full model:
[docs/business/ai-usage-limits.md](../business/ai-usage-limits.md).

## Recovery — the Celery-beat sweep

The AI-engine worker runs Celery beat with one periodic task, `ai_engine.recover_pending_ai_jobs`
(also fired on worker startup), which calls the backend's `POST /internal/ai/jobs/recover` →
`recover_all_ai_jobs`. Each beat:

- re-dispatches **due** durable jobs: retryable `failed` jobs past `next_retry_at`, `queued` jobs
  whose dispatch visibility timeout lapsed (covers broker loss and parked fair-use jobs — which
  re-defer while still over budget), and `running` jobs stale past
  `BACKEND_AI_JOB_RUNNING_STALE_SECONDS`;
- respects capture-chain ordering (only chain heads dispatch), and terminally marks jobs whose
  target capture/session was deleted;
- runs the **pending-synthesis catch-up sweep** (`sweep_pending_session_synthesis`): a safety net for
  the queue-collapse dispatch that re-triggers synthesis for a session left with an uncontributed
  capture and no active report job (e.g. a completion callback that never fired) — not a timer, it
  never delays a dispatch;
- runs the **patient-memory quiescence sweep** (`sweep_stale_patient_memory`): stale Pro patient
  memory whose visits have been idle ~30 min is refreshed at the lowest priority, capped per beat.

Retry backoff is bounded-exponential from `BACKEND_AI_JOB_RETRY_DELAY_SECONDS` up to
`BACKEND_AI_JOB_RETRY_MAX_DELAY_SECONDS`, with reasons classified (`gateway_unavailable`,
`source_missing`, `conversion_failed`, `invalid_output`, `worker_error`, `broker_unavailable`) for
triage. The worker supplies the reason directly (typed exceptions → codes; see
`docs/ai_engine/processing.md`); `classify_retry_reason` is only the fallback when it doesn't.
`invalid_output` marks a malformed/unusable model output (distinct from a gateway outage).

## Patient memory triggers (Pro)

The `patient_memory` job (summary + history) is **lazy**: it is never enqueued by synthesis
completion. It refreshes when staleness meets a read — the patient page or line-up recap opens
(priority 0), the patient is lined up (priority 3) — or via the background quiescence sweep
(priority 6). Dispatch self-gates on the `CROSS_VISIT_SYNTHESIS` capability, in-flight capture
jobs, and a per-patient dedup, so bursts coalesce and Basic tenants are a no-op.
