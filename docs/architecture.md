# Architecture

## Product Shape

AesMem is currently an MVP prototype for fast clinical capture. The primary workflow is:

1. Capture first.
2. Save locally immediately.
3. Sync to backend when possible.
4. Organize/review later.

The product should not feel like a dashboard, HIS, appointment system, queue manager, billing tool, or patient administration surface. The default landing destination after login is `Capture`, not patient search or a worklist.

## Current System

```text
Browser
  React prototype
  IndexedDB outbox and synced cache
  Vite dev proxy or nginx production proxy

Backend
  FastAPI API
  Celery producer for background AI job processing
  Redis broker/result backend
  Local filesystem capture storage
  JSON metadata per session

AI Engine
  Celery worker
  Placeholder audio/text/image capture processors

Storage
  Development: ./captures mounted to /data/captures
  Production: capture_data Docker volume mounted to /data/captures
```

## Backend v2 Direction

Backend v2 replaces file-backed JSON metadata with:

```text
Browser
  React frontend
  IndexedDB pending outbox
  IndexedDB synced preview cache
  Authenticated API client

Backend
  FastAPI API
  Backend-managed JWT auth
  Tenant-scoped services
  Celery-backed AI job producer

AI Engine
  Celery worker process
  AI processing implementation boundary

Storage
  Postgres metadata
  MinIO object storage
```

Postgres is the source of truth for tenants, users, patients, sessions, captures, artifacts, audit events, and processing job rows. MinIO stores source files and generated artifacts in both development and production.

Celery and Redis provide the background job boundary. The backend creates durable job rows and sends named tasks. `apps/ai_engine` consumes those tasks and owns the current placeholder implementations for audio capture processing, text capture processing, and image capture processing.

The AI engine does not import backend modules or connect directly to Postgres. It updates job lifecycle state through protected backend internal endpoints at `/internal/ai/jobs/...`. This keeps the backend as the owner of database schema, tenant scoping, audit events, and capture/job state while allowing the AI engine to evolve as a separate service. Real AI logic will replace the placeholder job bodies later.

## Data Flow

### Capture

1. User records audio, takes/selects a photo, or writes a note.
2. Browser writes the source blob into IndexedDB before attempting network upload.
3. UI marks the item as `Saved on device`.
4. The outbox attempts upload to the backend.
5. UI marks the item as `Syncing`.
6. Backend stores the source file and session metadata.
7. Backend creates a queued capture processing job and dispatches it to Celery.
8. Browser removes the pending outbox entry and keeps a synced local cache copy.
9. Celery marks the job `running`, writes placeholder generated metadata, and marks it `succeeded`; failures are retried and then marked `failed`.
10. UI updates to backend-safe states such as `Draft`, `Unassigned`, `Needs review`, `Processing`, or `Verified`.

### Session Save And Report Generation

The first uploaded capture creates a backend session in `draft` status. Draft
sessions are durable but are not considered saved for reporting. When the user
explicitly saves a session, the backend marks it `processing`, creates a queued
session job, and dispatches it to the AI engine.

The session job receives the session, captures, and a report template. The
current default template is markdown and has clinic information, patient
information, and body sections. The placeholder worker returns a generated
summary, structured extracted metadata, and a markdown report. Patient full name
and national ID are special extracted metadata fields because the backend can use
them for patient matching and the frontend can warn when they are missing.

When the session job succeeds, the backend stores the generated outputs on the
session and moves it to `needs_review` if a patient is assigned, otherwise
`unassigned`. Previous generated output snapshots are retained in session
metadata so future UI can fall back to earlier processed versions. Generated
output is still not clinically verified until staff verifies the session.

### Review

When previewing a capture, the frontend resolves the source in this order:

1. Pending local source from IndexedDB, if the capture has not synced.
2. Synced browser cache, if present.
3. Backend source file URL.

This keeps review fast while still allowing cache eviction after backend sync.

## Storage Model

Browser storage has two roles:

- `pendingCaptures`: local safety outbox for unsynced captures. These are not cache and must not be automatically deleted.
- `cachedCaptures`: synced local preview cache. These may be deleted when the cache exceeds the configured limit.

The current synced cache limit is `50 MB`. Eviction deletes the oldest/least recently accessed synced cached captures only. Unsynced data is preserved and should trigger warnings if it grows too large.

## Backend Storage

The backend currently stores captures on disk:

```text
captures/
  session-.../
    session.json
    cap-....jpg
    cap-....webm
    cap-....txt
```

This is intentionally simple for MVP testing. A production system should move source files to durable object storage and metadata to a real database.

Backend v2 uses Postgres for metadata and MinIO for object storage. The backend should not claim a capture is safely synced until the MinIO object and Postgres metadata are both durable.

## Session And Review Semantics

Patient selection is still not required before capture. Uploaded sessions and captures may remain unassigned until staff or AI processing assigns them.

Backend v2 separates organization from human verification:

- `draft`: captures exist, but the user has not explicitly saved the session.
- `unassigned`: no patient is known yet.
- `needs_review`: staff attention is needed.
- `processing`: AI processing is running.
- `organized`: legacy backend/AI organized state; new processing should route to `unassigned` or `needs_review`.
- `reviewing`: staff opened it for verification.
- `verified`: doctor or assistant reviewed and accepted it.
- `reopened`: verified session was sent back for changes.
- `failed`: processing failed; sources remain durable.

The frontend must not imply that generated content is clinically verified before `verified`.

## Design Decisions

- Capture is never blocked by patient selection.
- Capture is never blocked by background sync or processing.
- Browser IndexedDB is used as a local outbox because user data loss is unacceptable on slow or unreliable connections.
- Backend confirmation is the point where a capture is considered safely transferred.
- Synced browser cache is optional and evictable; unsynced browser data is not.
- User-facing capture states are compact and non-technical: `Saved on device`, `Syncing`, `Processing`, `Draft`, `Unassigned`, `Needs review`, `Verified`, `Failed/Retry`.
- Technical pipeline labels such as OCR, embedding, inference, or model names should not appear in doctor-facing UI.

## Known Prototype Limits

- Metadata is file-backed JSON, not a database.
- API is workflow-driven rather than full CRUD.
- There is no encryption-at-rest implementation yet.
- Browser storage quotas are not fully surfaced to the user yet.
- Audio recording on phone browsers may require HTTPS; a file input fallback exists for local HTTP testing.
