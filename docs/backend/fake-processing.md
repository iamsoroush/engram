# Fake Processing

## Summary

Fake processing gives the frontend realistic backend behavior for processing, transcripts, OCR, summaries, organization, and review states without introducing Celery, Redis, workers, or real AI.

This is non-production scaffolding. Keep it isolated so real jobs can replace it later.

## Scope

Included:

- Fake job rows in Postgres.
- Placeholder capture-processing job rows created at upload time.
- A five-second simulated capture-processing delay for local testing.
- Placeholder transcriptions for audio.
- Placeholder captions for photos.
- Placeholder decorated text for notes.
- Generated session summaries.
- Session transition to `organized`.

Excluded:

- Celery.
- Redis.
- Real AI/LLM calls.
- Real patient matching design.
- Long-running distributed job orchestration.

## Data Model

`fake_jobs` table:

- `id`
- `tenant_id`
- `job_type`: `capture_process`, `session_organize`
- `status`: `queued`, `running`, `succeeded`, `failed`
- `capture_id`, nullable
- `session_id`, nullable
- `started_at`, `completed_at`
- `error_message`, nullable
- `output` JSONB
- `created_by_user_id`
- `created_at`

Generated outputs should also be written to capture metadata, session fields, or artifact rows as appropriate.

Every generated output includes:

```json
{
  "generated_by": "fake-processing",
  "fake_job_id": "job_...",
  "generated_at": "2026-05-14T00:00:00Z"
}
```

## Capture Processing

On capture upload, the backend creates a placeholder `capture_process` job row and marks the capture `processing`.
Until real AI jobs are implemented, the API derives default generated-text metadata from the capture type. After about five seconds, subsequent capture responses expose the capture as `processed` with the relevant completed field:

- `metadata.transcript` for audio.
- `metadata.caption` for photo.
- `metadata.decorated_text` for text captures.

These upload-time placeholder jobs are intentionally minimal scaffolding. They do not create generated artifact rows yet.

Endpoint:

```text
POST /api/v1/captures/{capture_id}/fake-process
```

Behavior:

1. Validate auth, tenant access, and capture access.
2. Create a fake job row.
3. Mark capture `processing`.
4. Generate type-specific placeholder output.
5. Mark capture `processed`.
6. Store output in `captures.metadata` and artifact rows when useful.

Audio output:

- Transcript status becomes `completed`.
- Transcript text is plausible and clearly fake.
- Language defaults to `en` unless known.
- Duration/codec are copied from upload metadata if available.

Photo output:

- Caption status becomes `completed`.
- Caption text is a placeholder until real photo captioning exists.
- Dimensions are copied from upload metadata if available.
- Thumbnail artifact may be a placeholder reference if no real thumbnailing exists.

Note output:

- Decorated text status becomes `completed`.
- Decorated text preserves the captured note until real text decoration exists.
- Extraction status becomes `completed`.

## Session Organization

Endpoint:

```text
POST /api/v1/sessions/{session_id}/fake-organize
```

Behavior:

1. Validate auth, tenant access, and session access.
2. Create a fake job row.
3. Mark session `processing`.
4. Optionally fake-process unprocessed captures in that session.
5. Generate a short session summary from capture titles/details/metadata.
6. Set `organization_source=fake-processing`.
7. Move session to `organized`.

The session is not verified. A doctor or assistant must still use the review flow to move it to `verified`.

## Fake Patient Assignment

Fake processing may assign a session or capture to a seeded/demo patient only when the implementation has explicit deterministic demo rules. For example, a seeded note containing a seeded patient name may map to that seeded patient.

Do not build a general AI patient matching design in this version.

## Replacement Boundary

The future real processing system should be able to replace fake processing by:

- Keeping the same capture/session API surfaces.
- Reusing artifact rows.
- Reusing capture metadata schema where possible.
- Replacing `fake_jobs` with a real job table or mapping fake job concepts into the real job system.
- Preserving the distinction between `organized` and `verified`.
