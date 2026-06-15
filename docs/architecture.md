# Architecture

## Product Shape

Notari is currently an MVP prototype for fast clinical capture. The primary workflow is:

1. Capture first.
2. Save locally immediately.
3. Sync to backend when possible.
4. Organize/review later.

The product should not feel like a dashboard, HIS, appointment system, queue manager, billing tool, or patient administration surface. The default landing destination after login is `Capture`, not patient search or a worklist.

## Current System

```text
Browser
  React frontend
  IndexedDB pending outbox
  IndexedDB synced preview cache
  Authenticated API client
  Vite dev proxy or nginx production proxy

Backend
  FastAPI API
  Backend-managed JWT auth
  Tenant-scoped services
  Celery producer for background AI job processing
  Redis broker/result backend
  Alembic-managed schema

AI Engine
  Celery worker process
  Placeholder audio/text/image capture processors

Storage
  Postgres metadata
  MinIO object storage (development and production)
```

Postgres is the source of truth for tenants, users, patients, sessions, captures, artifacts, audit events, and processing job rows; the schema is managed with Alembic. MinIO stores source files and generated artifacts in both development and production. See [backend design](backend/design.md), [storage](backend/storage.md), [auth](backend/auth.md), and [production](production.md) for details.

Celery and Redis provide the background job boundary. The backend creates durable job rows and sends named tasks. `apps/ai_engine` consumes those tasks and owns the current placeholder implementations for audio capture processing, text capture processing, and image capture processing.

The AI engine does not import backend modules or connect directly to Postgres. It updates job lifecycle state and partial progress through protected backend internal endpoints at `/internal/ai/jobs/...`. This keeps the backend as the owner of database schema, tenant scoping, audit events, and capture/job state while allowing the AI engine to evolve as a separate service. Real AI logic will replace the placeholder job bodies later.

## Data Flow

### Capture

1. User records audio, takes/selects a photo, or writes a note.
2. Browser writes the source blob into IndexedDB before attempting network upload.
3. UI confirms local safety using the shared UX state language.
4. The outbox attempts upload to the backend when possible.
5. Backend stores the source file and session metadata.
6. Backend creates a queued capture processing job and dispatches it to Celery.
7. Browser removes the pending outbox entry and keeps a synced local cache copy.
8. Celery marks the job `running`, writes partial placeholder generated metadata, waits briefly, and marks it `succeeded`; failures are retried and then marked `failed`.
9. UI updates through assistant-style states owned by [UX states](ux/states.md).

### Session Evolution And Report Generation

The first uploaded capture creates a durable backend session in `draft` status.
Sessions are continuously evolving objects: new captures can be added in any
state, and every session response includes frontend-stable `report`,
`summaries`, `findings`, and `processingStatus` contracts.

Phase 2.1 uses deterministic mocked session evolution instead of real AI. Capture
upload updates the same session with a partial report draft, summary, extracted
finding rows, and processing status metadata. Phase 2.2 adds fake async worker
stages that post partial transcript, report, finding, and summary updates over
time.

The explicit session processing endpoint remains available as a report refresh
hook, but it is no longer the workflow gate that makes a session reviewable or
editable. The live report is now rebuilt **deterministically and synchronously** (no LLM, no
`session_organize` job) once a session's capture chain is idle; the backend stores the report and
moves the session to `needs_review` if a patient is assigned, otherwise `unassigned`. Completion is
auto-derived (`complete`) — there is no manual verify step.

Structured report content is stored in `sessions.report_model` as the backend
source of truth. Markdown remains a rendered/export format in the session
contract. Session processing receives a versioned context with the raw report
template, clinic context, assigned DB patient context, patient history summary,
processed capture outputs, artifact URLs, and session metadata. Its completed
output is body-level structured content only: sections, image/artifact
references, source capture references, extracted findings, and an optional
summary. The default singleton report template renders clinic information,
patient information, and body sections; patient information is injected from the
assigned patient record and identifiers, not from AI-generated body text. The
current template key is `default`.

### Review

When previewing a capture, the frontend resolves the source in this order:

1. Pending local source from IndexedDB, if the capture has not synced.
2. Synced browser cache, if present.
3. Backend source file URL.

This keeps review fast while still allowing cache eviction after backend sync.

## Entity Model (verticals)

`Patient` is **universal** across verticals and stays the assignment target. What varies by
vertical is the **report-required work-unit** — a capture-first **Session**/**Visit**, a radiology
**Study**, a pathology **Case** — modeled as one generic **Encounter** (`Patient 1—* Encounter 1—*
Capture`, one `Report` per Encounter). The Encounter **is** today's `Session` (no `Session →
Encounter` rename yet).

- `tenant.vertical` (`aesthetics` | `therapy` | `dermatology` | `radiology` | `pathology`; default
  `aesthetics`) types the workspace. The Spine-A verticals (aesthetics/therapy/dermatology) share
  the capture-first core. The legacy `clinic` value normalizes to `aesthetics` (the current
  product).
- The work-unit **presentation label** is derived from the vertical via
  [`services/verticals.encounter_label`](../apps/backend/app/services/verticals.py)
  (aesthetics/therapy→"Session", dermatology→"Visit", radiology→"Study", pathology→"Case") and
  surfaced on the `TenantProfile` (`vertical`, `encounterLabel`) — it must not be hardcoded in
  core/apply logic.
- `session.attributes` (JSONB) is a reserved per-vertical extension point (radiology:
  accession/modality/body_part; pathology: specimen_id/stain), kept separate from
  `extracted_metadata` (AI/processing output). Empty for capture-first verticals.

The literal `Session → Encounter` rename and per-vertical `attributes` fields land with the second
vertical. See [intelligence-layer.md §2](intelligence-layer.md) for the full rationale.

## Storage Model

Browser storage has two roles:

- `pendingCaptures`: local safety outbox for unsynced captures. These are not cache and must not be automatically deleted.
- `cachedCaptures`: synced local preview cache. These may be deleted when the cache exceeds the configured limit.
- `pendingOperations`: lightweight local work that must replay after backend IDs exist, such as session titles, patient assignment/create intent, and report generation requests.

The current synced cache limit is `50 MB`. Eviction deletes the oldest/least recently accessed synced cached captures only. Unsynced data is preserved and should trigger warnings if it grows too large.

## Backend Storage

The backend stores metadata in Postgres and source files plus generated artifacts in MinIO (S3-compatible object storage), in both development and production. Object keys are tenant-scoped and never expose patient names or source filenames; file access goes through backend authorization or short-lived presigned URLs.

The backend does not claim a capture is safely synced until the MinIO object and its Postgres metadata are both durable. If either side fails, the upload must not return success. See [storage](backend/storage.md) for object-key layout, upload-safety, and backup requirements.

## Session And Review Semantics

Patient selection is not required before capture. Uploaded sessions and captures may remain unassigned until staff or AI processing assigns them.

The backend separates organization from human verification:

- `draft`: captures exist and the session is still in active capture/progressive draft state.
- `unassigned`: no patient is known yet.
- `needs_review`: staff attention is needed.
- `processing`: AI processing is running.
- `organized`: deprecated backend/AI organized state; new processing should route to `unassigned` or `needs_review`.
- `reviewing`: staff opened it for review.
- `verified`: **deprecated** — manual verification was removed. Completion is now auto-derived
  (`complete` = captures processed + patient assigned + report current); the enum value is retained
  only for historical rows and is no longer set.
- `reopened`: session was sent back for changes.
- `failed`: processing failed; sources remain durable.

Sessions remain editable and reviewable in every state; states describe attention
or confidence rather than access. A session's **complete** flag (auto-derived, surfaced on the
session payload) replaces the old manual "verify" gate.

## Design Decisions

- Capture is never blocked by patient selection.
- Capture is never blocked by background sync or processing.
- Browser IndexedDB is used as a local outbox because user data loss is unacceptable on slow or unreliable connections.
- Offline support is capture-first with local drafts, not a full offline patient registry.
- Backend confirmation is the point where a capture is considered safely transferred.
- Synced browser cache is optional and evictable; unsynced browser data is not.
- AI jobs are durable backend work. Queued and retryable failed jobs can be re-dispatched when workers recover.
- User-facing capture states are compact, non-technical, and owned by [UX states](ux/states.md).
- Technical pipeline labels such as OCR, embedding, inference, job queues, or model names should not appear in doctor-facing UI.

## Known Limits

- AI capture/session processing is still placeholder logic, not real models.
- There is no encryption-at-rest implementation yet.
- Browser storage quotas are not fully surfaced to the user yet.
- Audio recording on phone browsers may require HTTPS; a file input fallback exists for local HTTP testing.
