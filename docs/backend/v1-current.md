# Backend v1 Current Prototype

## Stack

- Python 3.12
- FastAPI
- uvicorn
- `python-multipart` for upload handling

Main app:

```text
apps/backend/app/main.py
```

Settings:

```text
apps/backend/app/config.py
```

## Current API

The current API is intentionally minimal and prototype-oriented.

```text
GET   /api/v1/health
GET   /api/v1/message
GET   /api/v1/sessions
POST  /api/v1/captures
PATCH /api/v1/sessions/{session_id}/organize
GET   /api/v1/files/{session_id}/{filename}
```

`POST /api/v1/captures` accepts multipart form data:

```text
capture_type: audio | photo | note
session_id: optional backend session id
new_session: boolean
detail: optional text
file: uploaded source blob
```

If no backend session exists, the endpoint creates one. This is convenient for the local-first prototype, but it is not the final API shape.

## Current Storage

Development Compose mounts:

```text
./captures:/data/captures
```

The backend writes:

```text
/data/captures/
  session-.../
    session.json
    cap-....jpg
    cap-....webm
    cap-....txt
```

`session.json` is the metadata source of truth for now. This should be replaced by a database before real production use.

## Status Model

Internal frontend-only local states:

- local source saved
- upload in progress
- upload failed while local outbox still has the source

Backend states begin only after upload is accepted:

- `needsReview`
- `organized`
- future: `received`, `processing`, `failed`

The backend should not claim a source is safely stored until the file write and metadata write both succeed.

User-facing labels are owned by [UX states](../ux/states.md).

## API Design Direction

The current API is not full CRUD. That is acceptable for MVP, but future backend work should move toward resource endpoints plus workflow actions.

Expected resource endpoints:

```text
GET    /api/v1/sessions
POST   /api/v1/sessions
GET    /api/v1/sessions/{session_id}
PATCH  /api/v1/sessions/{session_id}
DELETE /api/v1/sessions/{session_id}

GET    /api/v1/sessions/{session_id}/captures
POST   /api/v1/sessions/{session_id}/captures
GET    /api/v1/captures/{capture_id}
PATCH  /api/v1/captures/{capture_id}
DELETE /api/v1/captures/{capture_id}
GET    /api/v1/captures/{capture_id}/file
```

Expected workflow endpoints:

```text
POST /api/v1/sessions/{session_id}/organize
POST /api/v1/sessions/{session_id}/start-review
POST /api/v1/captures/{capture_id}/retry-processing
```

The local-first frontend can create local IDs before backend IDs exist. A cleaner long-term sync model is:

1. Frontend creates local session/capture in IndexedDB.
2. Frontend calls `POST /sessions` when online.
3. Frontend uploads each capture through `POST /sessions/{session_id}/captures`.
4. Backend returns stable IDs.
5. Frontend stores a local-to-backend ID mapping.

## Production Backend Requirements

Before real clinical use, add:

- authentication and authorization;
- user, clinic, and tenant isolation;
- database-backed metadata;
- durable object storage for files;
- encryption at rest;
- malware/file validation where appropriate;
- audit logs for capture access and organization;
- request size limits and upload timeout handling;
- background processing jobs separate from request handling;
- backup and restore strategy.

Backend v2 intentionally uses AI processing instead of real background workers. See [backend v2 design](v2-design.md) and [AI engine processing](../ai_engine/processing.md).

## Development Commands

```sh
docker compose up --build backend
```

Local Python workflow:

```sh
cd apps/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```
