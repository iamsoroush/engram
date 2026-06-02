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
- Placeholder captions for photos.
- Placeholder decorated text for notes.
- Capture-level detected-patient schema for future patient assignment.
- Generated session summaries.
- Generated session extracted metadata, including patient full name and national ID.
- Generated body-level structured session reports rendered through backend-owned report templates.
- Session transition to `unassigned` or `needs_review` after processing.

Excluded:

- Real AI/LLM calls for photo, note, session organization, and patient matching.
- Real patient matching design.
- Long-running distributed job orchestration.

## Data Model

`ai_jobs` table:

- `id`
- `tenant_id`
- `job_type`: `audio_capture_process`, `text_capture_process`, `image_capture_process`, `capture_process`, `session_organize`
- `status`: `queued`, `running`, `succeeded`, `failed`
- `capture_id`, nullable
- `session_id`, nullable
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
6. Audio jobs download the source capture through the protected backend internal API and transcribe it when `AI_ENGINE_TRANSCRIPTION_BASE_URL` is configured; photo and note jobs wait briefly to simulate asynchronous processing.
7. Worker writes type-specific completed output.
8. Worker marks capture `processed` and job `succeeded`.

If a worker attempt raises, the task logs the exception, stores the last error
and retry reason in the job row, and lets Celery perform its bounded local
retry. The backend also stores `next_retry_at` using bounded backoff. After
Celery retries are exhausted, retryable jobs remain durable `failed` rows that
periodic recovery will re-dispatch when due. Capture rows remain in
`processing` for retryable operational failures so normal UX can continue to
say the material is saved and organizing. Deleted capture/session targets are
marked non-retryable and skipped by recovery.

Audio output:

- Transcript status becomes `completed`.
- Transcript text is generated from the source audio when transcription is configured; otherwise it remains plausible placeholder text.
- Language defaults to `en` unless known.
- Duration/codec are copied from upload metadata if available.
- `detected_patient` is present on audio output and currently always returns
  `status=not_detected` with null patient fields.
- The detected-patient schema supports `full_name`, `national_id`,
  `confidence`, `evidence`, `source_text`, and `status`.

Photo output:

- Caption status becomes `completed`.
- Caption text is a placeholder until real photo captioning exists.
- Dimensions are copied from upload metadata if available.
- Thumbnail artifact may be a placeholder reference if no real thumbnailing exists.

Note output:

- Decorated text status becomes `completed`.
- Decorated text preserves the captured note until real text decoration exists.
- Extraction status becomes `completed`.

The deterministic QA fixture under `test_data/` is recognized by capture
filename/content. Uploading those captures produces predictable transcript,
caption, decorated text, session structured report sections, and rendered
markdown so ingestion, capture processing, session processing, report model
conversion, and markdown rendering can be tested end to end.

## Session Evolution And Organization

Endpoint:

```text
POST /api/v1/sessions/{session_id}/save
```

Report refresh behavior:

1. Validate auth, tenant access, and session access.
2. Accept the request in any session state.
3. If captures exist, mark session `processing`, create a queued `session_organize` job row, and dispatch `ai_engine.process_session` through Celery.
4. Worker receives the session, captures, and report template.
5. Worker receives a stable `sessionProcessingContext` containing the raw report template, clinic context, assigned DB patient context when available, patient history summary when available, processed audio/photo/text capture outputs, artifact URLs, and session metadata.
6. Worker posts deterministic partial updates for transcript review, report drafting, finding extraction, and summary generation.
7. Worker writes completed placeholder session summary, structured extracted metadata, and a body-level `structured_report` output.
8. Backend converts `structured_report` into `sessions.report_model`, then renders markdown from that model.
9. Backend stores the generated outputs on the session.
10. Backend sets `organization_source=ai-engine`.
11. Backend moves the session to `needs_review` when a patient is assigned, otherwise `unassigned`.

Capture upload behavior:

1. Attach the capture to the requested session regardless of session state.
2. Update deterministic mocked progressive session contracts.
3. Preserve review/edit access; state changes are informative and do not gate use.

The session is not verified. A doctor or assistant must still use the review flow to move it to `verified`.

Session processing can be retried with:

```text
POST /api/v1/sessions/{session_id}/retry-processing
```

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

## AI Patient Assignment

AI processing may assign a session or capture to a seeded/demo patient only when the implementation has explicit deterministic demo rules. For example, a seeded note containing a seeded patient name may map to that seeded patient.

Do not build a general AI patient matching design in this version. Session-level
AI output may produce a deterministic `patient_match` metadata candidate, but it
must not overwrite the session's DB-owned patient assignment.

## Replacement Boundary

The future real processing system should be able to replace AI processing by:

- Keeping the same capture/session API surfaces.
- Reusing artifact rows.
- Reusing capture metadata schema where possible.
- Replacing `ai_jobs` with a real job table or mapping AI job concepts into the real job system.
- Preserving the distinction between generated output and human `verified` state.
