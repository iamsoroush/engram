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
  Local filesystem capture storage
  JSON metadata per session

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
  Fake processing endpoints

Storage
  Postgres metadata
  MinIO object storage
```

Postgres is the source of truth for tenants, users, patients, sessions, captures, artifacts, audit events, and fake job rows. MinIO stores source files and generated artifacts in both development and production.

Celery, Redis, and real AI jobs are intentionally out of scope for v2. Fake processing gives the frontend realistic transcripts, OCR, summaries, and organization states until real processing is designed.

## Data Flow

### Capture

1. User records audio, takes/selects a photo, or writes a note.
2. Browser writes the source blob into IndexedDB before attempting network upload.
3. UI marks the item as `Saved on device`.
4. The outbox attempts upload to the backend.
5. UI marks the item as `Syncing`.
6. Backend stores the source file and session metadata.
7. Browser removes the pending outbox entry and keeps a synced local cache copy.
8. UI updates to backend-safe states such as `Unassigned`, `Needs review`, `Processing`, `Organized`, or `Verified`.

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

Patient selection is still not required before capture. Uploaded sessions and captures may remain unassigned until staff or fake processing assigns them.

Backend v2 separates organization from human verification:

- `unassigned`: no patient is known yet.
- `needs_review`: staff attention is needed.
- `processing`: fake processing is running.
- `organized`: backend/fake processing has organized the session.
- `reviewing`: staff opened it for verification.
- `verified`: doctor or assistant reviewed and accepted it.
- `reopened`: verified session was sent back for changes.
- `failed`: processing failed; sources remain durable.

The frontend must not imply that `organized` content is clinically verified.

## Design Decisions

- Capture is never blocked by patient selection.
- Capture is never blocked by background sync or processing.
- Browser IndexedDB is used as a local outbox because user data loss is unacceptable on slow or unreliable connections.
- Backend confirmation is the point where a capture is considered safely transferred.
- Synced browser cache is optional and evictable; unsynced browser data is not.
- User-facing capture states are compact and non-technical: `Saved on device`, `Syncing`, `Processing`, `Unassigned`, `Organized`, `Verified`, `Needs review`, `Failed/Retry`.
- Technical pipeline labels such as OCR, embedding, inference, or model names should not appear in doctor-facing UI.

## Known Prototype Limits

- Metadata is file-backed JSON, not a database.
- API is workflow-driven rather than full CRUD.
- There is no authentication or user/clinic isolation yet.
- There is no encryption-at-rest implementation yet.
- Browser storage quotas are not fully surfaced to the user yet.
- Audio recording on phone browsers may require HTTPS; a file input fallback exists for local HTTP testing.
