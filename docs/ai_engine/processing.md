# AI Processing

## Summary

AI processing originally gave the frontend realistic backend behavior for processing, transcripts, OCR, summaries, organization, and review states without workers. Capture processing now uses the real Celery and Redis job boundary, but the job bodies still write deterministic placeholder output until real AI processors are implemented.

This is non-production scaffolding. Keep it isolated so real jobs can replace it later.

Phase 2.1 added deterministic mocked session evolution directly to the backend
session model. Phase 2.2 adds fake asynchronous worker stages from
`apps/ai_engine`: jobs post partial progress before final completion so the
frontend can render visible evolution over time.

## Scope

Included:

- Processing job rows in Postgres.
- Queued capture-processing job rows created at upload time.
- Celery/Redis dispatch for capture jobs.
- Retry-aware job status updates and worker logging.
- Internal progress callback for partial outputs.
- Real audio transcription through a configured OpenAI-compatible gateway.
- Real Pro image captions and note decoration through the same gateway (tier-gated; Basic and
  gateway-less/fixture captures keep the deterministic placeholders).
- Real combined patient **summary + history** synthesis (Pro) via the `patient_memory` job
  (gateway-backed, with a deterministic fallback). Live per-task model selection.
- Capture-level detected-patient schema and deterministic patient assignment provenance.
- Generated session summaries.
- Generated session extracted metadata, including patient full name and national ID.
- Generated body-level structured session reports rendered through backend-owned report templates.
- Session transition to `unassigned` or `needs_review` after processing.

Excluded:

- Real AI/LLM calls for session organization (synthesis) and patient matching ranking.
- Duplicate merging, whole-table LLM patient search, or automatic assignment from ambiguous matches.
- Long-running distributed job orchestration.

## Data Model

`ai_jobs` table:

- `id`
- `tenant_id`
- `job_type`: `audio_capture_process`, `text_capture_process`, `image_capture_process`, `capture_process`, `session_organize`, `patient_memory`
- `status`: `queued`, `running`, `succeeded`, `failed`
- `capture_id`, nullable
- `session_id`, nullable
- `patient_id`, nullable (used by patient-scoped `patient_memory` jobs)
- `started_at`, `completed_at`
- `error_message`, nullable
- durable retry schedule fields:
  - `attempt_count`
  - `last_attempted_at`
  - `last_dispatched_at`
  - `next_retry_at`
  - `last_error`
  - `retry_reason`
- `output` JSONB
- `created_by_user_id`
- `created_at`

Generated outputs should also be written to capture metadata, session fields, or artifact rows as appropriate.

Every generated output includes:

```json
{
  "generated_by": "ai-engine",
  "ai_job_id": "job_...",
  "generated_at": "2026-05-14T00:00:00Z"
}
```

## Capture Processing

On capture upload, the backend creates a queued capture processing job row and marks the capture `processing`. The backend dispatches the job to Celery after the source object and metadata transaction is durable. The worker marks the job `running`, posts one partial generated-text update, and then marks the capture `processed` with the relevant completed field:

- `metadata.transcript` for audio.
- `metadata.caption` for photo.
- `metadata.decorated_text` for text captures.

Audio jobs can call a configured gateway. Photo and note jobs remain intentionally minimal placeholder scaffolding. Capture jobs do not create generated artifact rows yet.

Manual enqueue endpoint:

```text
POST /api/v1/captures/{capture_id}/retry-processing
```

Behavior:

1. Validate auth, tenant access, and capture access.
2. Create a AI job row.
3. Mark capture `processing`.
4. Dispatch a Celery task.
5. Worker writes type-specific partial output.
6. Audio jobs download the source capture through the protected backend internal API and transcribe it through the configured `AI_ENGINE_TRANSCRIPTION_BASE_URL`; photo and note jobs wait briefly to simulate asynchronous processing.
7. Worker writes type-specific completed output.
8. Worker marks capture `processed` and job `succeeded`.

If a worker attempt raises, the task logs the exception, stores the last error
and retry reason in the job row, and lets Celery perform its bounded local
retry. The backend also stores `next_retry_at` using bounded backoff. After
Celery retries are exhausted, retryable jobs remain durable `failed` rows that
periodic recovery will re-dispatch when due. Capture rows remain in
`processing` for retryable operational failures so normal UX can continue to
show a generic processing state. Deleted capture/session targets are
marked non-retryable and skipped by recovery.

Audio output:

- Transcript status becomes `completed`.
- Transcript text is generated from the source audio through the configured transcription gateway. Non-fixture audio jobs do not write placeholder transcript text when the gateway is missing; they stay on the retryable job path instead.
- Configured transcription jobs receive a tenant-scoped `transcriptionContext` containing clinic assumptions, assigned patient context when present, session metadata, previous same-session transcripts, same-session text notes, and safe assigned-patient history summary when available.
- Configured transcription jobs ask the gateway for strict structured JSON with `transcript`, `language`, `patient_information`, `clinical_summary`, and `uncertainties`. Malformed structured output is treated as a retryable worker failure.
- Language is one of `fa`, `en`, `mixed`, or `unknown`.
- Duration/codec are copied from upload metadata if available.
- After structured `patient_information` is stored with explicit identity evidence, such as a spoken name or identifier, the backend creates a deterministic `patient_match_candidate`. A deterministic existing match is assigned automatically with AI provenance. A true no-match with usable extracted identity creates an AI-origin patient, assigns the session, and marks the created patient as needing staff verification. Each patient assignment/create action is appended to `patient_assignment_timeline`; the latest valid event becomes `active_patient_assignment_action`. Deleted capture-backed events are skipped when recomputing the active assignment, while later manual assignment remains authoritative over older AI events.
- `detected_patient` remains present as a compatibility projection of structured `patient_information`.

Photo output:

- Caption status becomes `completed`.
- **Pro:** caption text is generated by the configured multimodal gateway (the source image is
  downloaded through the internal API and sent as an OpenAI-compatible `image_url` data URL). The
  caption describes only what is clinically visible and stays in the source language/native script
  (no romanization). **Basic:** photos get **no AI caption** (blank) so the UI offers a manual
  "Add caption" rather than a placeholder. **No gateway / empty response:** also blank. **QA
  fixtures:** keep their deterministic caption. The Pro gate is the presence of `enrichmentContext`
  on the worker payload (below).
- Dimensions are copied from upload metadata if available.
- Thumbnail artifact may be a placeholder reference if no real thumbnailing exists.

Note output:

- Decorated text status becomes `completed`.
- **Pro:** the captured note is lightly decorated by the configured gateway (typos/shorthand
  cleaned, organized into clinical phrasing) while preserving every detail, number, and instruction
  and adding nothing; output stays in the source language/native script. **Basic / no gateway / QA
  fixtures:** decorated text preserves the captured note verbatim (passthrough placeholder).
- Extraction status becomes `completed`.

Per-task models (live-selectable):

- Each AI task (`transcription`, `caption`, `note_decoration`, `patient_memory`) can run on its own
  model. The model id is **live-configurable at runtime, globally**: the backend stores a per-task
  override in the `app_config` table (key `ai_models`), editable via `GET`/`PUT
  /api/v1/ai-config/models` (Settings → AI models) and surfaced to the worker in every job payload as
  `aiModels`. The worker resolves the model as: payload `aiModels[task]` → env `AI_ENGINE_<TASK>_MODEL`
  → env `AI_ENGINE_TRANSCRIPTION_MODEL` (`resolve_model` / `gateway_settings_for`). Because the
  backend reads the override when it builds the payload at job `/start`, a change takes effect on the
  **next request** with no restart.
- Gateway URL/key stay in env only (`AI_ENGINE_<TASK>_BASE_URL` / `_API_KEY`, blank → the shared
  `transcription_*` gateway). Only the model id is live; secrets are not stored in the DB.

Pro enrichment gating (photo captions + note decoration):

- Captions and note decoration are **Pro-tier** capabilities (see the tier table in
  `docs/intelligence-layer.md` §3). The backend gates them at the worker-payload boundary: it
  attaches an `enrichmentContext` (`2026-06-06.capture-enrichment-context.v1` — clinic, assigned
  patient, preferred language, capture type) to a photo/note job **only when `tenant.tier == "pro"`**
  (reusing the existing `tenant_tier` gate). A Basic tenant's worker never receives the context and
  never calls the gateway, so it keeps the deterministic placeholder/passthrough.
- The worker stays a pure function of its payload: it enriches iff `enrichmentContext` is present
  **and** a gateway is configured **and** the capture is not a QA fixture; otherwise it writes the
  placeholder. The output key is unchanged (`caption` / `decorated_text`), so the worker contract
  stays stable. A gateway error propagates as a retryable worker failure (self-healing); an empty
  gateway response falls back to the placeholder so the capture still completes.

**Vertical-agnostic prompts (all capture + memory jobs).** No processor hardcodes a vertical. The
backend resolves the tenant's vertical to a `domain` descriptor (`label` + optional `vocabulary` /
`captionFindings` — `app/services/verticals.py:domain_descriptor`) and includes it in the
transcription/enrichment context and the patient-memory payload. Each prompt builder reads it via
`processing.domain_framing()`, which falls back to a neutral `"clinic"` with no vocabulary when the
descriptor is absent — so the same worker serves aesthetics, therapy, and future verticals, and a
tenant is never told it is the wrong kind of clinic. Add a vertical's wording by extending
`domain_descriptor`, never by editing the prompts. See the README caution.

The deterministic QA fixture under `test_data/` is recognized by capture
filename/content. Uploading those captures produces predictable transcript,
caption, decorated text, session structured report sections, and rendered
markdown so ingestion, capture processing, session processing, report model
conversion, and markdown rendering can be tested end to end.

## Session Report Generation (deterministic, no AI job)

The live report is **not** produced by an AI/worker job. Once a session's capture chain is idle, the
backend rebuilds the report **synchronously and deterministically** from the session's processed,
in-context captures (`regenerate_session_report` / `regenerate_session_report_if_idle` in
`ai_jobs.py`). There is no `session_organize` Celery task, no LLM, and no "updating" churn — the
report is always current for the latest capture.

- **Basic:** one chronological `Clinical report` section. **Pro:** fixed by-type sections
  (`Audio notes` / `Written notes` / `Photos`); photos render as image blocks. Out-of-context
  captures are excluded; Pro records each folded-in capture's `report_contribution` and the
  included/set-aside meta counts.
- Triggered after the capture chain drains (capture completion), on capture delete / "mark relevant",
  and by `POST /api/v1/sessions/{session_id}/save` (now a synchronous rebuild) and
  `POST /api/v1/sessions/{session_id}/retry-processing`.
- The backend sets `organization_source=ai-engine` and moves the session to `needs_review` when a
  patient is assigned, otherwise `unassigned`.

**Completion is auto-derived** (no manual verify): a session is *complete* when its captures are
processed, a patient is assigned, and the report is current (not stale). Editing/adding a capture
marks the report stale and flips the session back to incomplete until it regenerates.

> The legacy `session_organize` worker path (`run_session_processing_job` /
> `complete_session_worker_job`) is retained only to gracefully drain any in-flight jobs; nothing
> creates new ones.

## Patient Memory (combined summary + history, Pro)

The patient-level **summary** (card) and **history** (timeline brief) are produced by a single
real AI job, `patient_memory` (patient-scoped via `ai_jobs.patient_id`). One model call returns
both — shared context (≈half the input cost) and a card summary guaranteed consistent with the
history.

- **Incremental input.** The payload (`build_patient_memory_job_input`) carries the patient's
  *prior* memory plus compact per-visit briefs (each session's distilled summary + capture
  counts/types), not raw transcripts — so cost stays ~flat as visits grow. It also includes a
  `deterministicFallback` (the backend's deterministic generator output).
- **Worker** (`completed_patient_memory_output`): when a gateway is configured it asks the model for
  strict JSON (`summary` + `history{snapshot, sections, visits}`) and validates it; if the gateway is
  absent or the response is unusable it returns the `deterministicFallback`, so the job always
  completes with valid memory. Output `source` is `ai:<model>` or `mock-deterministic`.
- **Dispatch gate (report-complete).** `maybe_dispatch_patient_memory_job` is **Pro-only** and runs
  only once the triggering session is *complete* — captures processed, a patient assigned (manual or
  auto-matched), report current — and no capture job is still in flight for the patient. It coalesces
  bursts per patient (dedup on an in-flight `patient_memory` job). Triggers: capture-chain settle
  (`complete_worker_job`) and patient (re)assignment (both sides). Recovery re-dispatches it like
  other jobs.
- **Completion** (`complete_patient_memory_worker_job`) writes `patients.memory`
  (`status:"ready", summary, history, source, updated_at`); the read path serves the stored brief.
- **Basic** never runs this job — its summary/history are deterministic, finalized lazily on read. A
  Pro read only finalizes deterministically as a safety net when nothing is in flight, so Pro memory
  is never permanently stuck in `updating`.

Capture upload behavior:

1. Attach the capture to the requested session regardless of session state.
2. The report is rebuilt deterministically once the capture chain settles.
3. Preserve review/edit access; state changes are informative and do not gate use.

Processing job rows are exposed through AI job routes:

```text
GET /api/v1/ai-jobs/{job_id}
GET /api/v1/sessions/{session_id}/ai-jobs
POST /api/v1/ai-jobs/recover
```

Internal worker progress endpoint:

```text
POST /internal/ai/jobs/{job_id}/progress
POST /internal/ai/jobs/recover
```

This endpoint is intentionally small: it persists partial capture metadata or
partial session contracts and leaves the job `running`. Real AI integration can
replace the mock stage producer without changing the frontend contract shape.

## Recovery Behavior

AI jobs are durable backend rows. Queued jobs, retryable failed jobs whose
`next_retry_at` has arrived, and stale running jobs can be re-dispatched after
broker or worker downtime. Staff/admin users can call the public recovery
endpoint, AI workers call the internal recovery endpoint when they come online,
and the AI engine also runs a periodic recovery task through Celery Beat so
delayed work resumes without requiring a user action or a fresh worker start.

Failed jobs carry retry metadata and durable retry columns. A job with
`result_metadata.retryable=false` is treated as terminal/manual-attention work
and is skipped by recovery. Backend-owned target checks mark jobs for deleted
captures or sessions non-retryable so they do not retry forever.

## Session Processing Contract

The session processing input schema is versioned as
`2026-05-21.session-processing-input.v1`. It includes:

- `rawReportTemplate`
- `clinic`
- `assignedPatient`, from DB assignment only
- `patientSummarizedHistory`
- processed `captures.audio`, `captures.photos`, and `captures.text`
- `session` metadata

The completed output schema is versioned as
`2026-05-21.session-processing-output.v1`. It contains body-level content only:

- report `sections` with paragraph/image/artifact blocks
- `artifactReferences`
- `sourceReferences`
- extracted `findings`
- optional `summary`

Clinic and patient information are intentionally excluded from generated report
body output. The backend renders those fields from template and database state.

## AI Patient Matching

Patient matching is backend-owned and reviewable. The backend preserves
`Patient.display_name` exactly as staff entered it and stores deterministic
search aliases in `patient_identifiers`.

On patient create/update, the backend generates normalized identifiers and
aliases for:

- national ID, normalized to digits only
- phone, including Iranian `+98` normalization when possible
- email, lowercased
- staff-entered display/legal names, including Arabic/Persian character
  variants, digit normalization, punctuation/whitespace normalization, and
  rough Persian-to-Latin aliases

After capture transcription or session organization provides structured
`patient_information`, matching runs in this order:

1. exact national ID
2. exact phone or email
3. exact normalized alias
4. fuzzy alias candidate search
5. optional LLM ranking only over the small backend-selected candidate set

The LLM step is optional and ranking-only. It must not search all patients,
create patients, assign sessions, merge patients, or rewrite display names.

Matching output is stored as `patient_match_candidate` on capture metadata and,
for unassigned sessions, mirrored into session extracted metadata. Deterministic
`matched` results assign the existing patient and store `ai_patient_action`
provenance. Deterministic `no_match` results create and assign an AI-origin
patient only when extracted identity has a usable name or identifier; the active
screen asks staff to complete and verify the created record. If a session already
has a DB-owned patient assignment, generated identity is skipped as an assignment
source and cannot override it. Ambiguous and insufficient results remain
human-decision work for assignment/choice resolvers.

## Replacement Boundary

The future real processing system should be able to replace AI processing by:

- Keeping the same capture/session API surfaces.
- Reusing artifact rows.
- Reusing capture metadata schema where possible.
- Replacing `ai_jobs` with a real job table or mapping AI job concepts into the real job system.
- Preserving the distinction between generated output and human `verified` state.
