# Fake Processing

## Summary

Fake processing gives the frontend realistic backend behavior for processing, transcripts, OCR, summaries, organization, and review states without introducing Celery, Redis, workers, or real AI.

This is non-production scaffolding. Keep it isolated so real jobs can replace it later.

## Scope

Included:

- Fake job rows in Postgres.
- Inline or FastAPI background-task execution.
- Placeholder transcripts for audio.
- Placeholder OCR and descriptions for photos.
- Normalized text for notes.
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

- OCR status becomes `completed`.
- OCR text or description is plausible and clearly fake.
- Dimensions are copied from upload metadata if available.
- Thumbnail artifact may be a placeholder reference if no real thumbnailing exists.

Note output:

- Normalized text trims whitespace and preserves clinical content.
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
