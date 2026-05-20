# Backend v2 Design

## Summary

Backend v2 is the handoff target for replacing the prototype storage model. It uses FastAPI, Postgres for metadata, MinIO for source files and generated artifacts, backend-managed JWT authentication, tenant-scoped authorization, patient-aware sessions and captures, and Celery-backed processing jobs with realistic placeholder outputs from `apps/ai_engine`.

The backend must continue to support local-first frontend capture. A capture is only considered safely transferred after the source object is stored in MinIO and its metadata is committed in Postgres.

Celery and Redis provide the background processing boundary. The backend produces tasks and `apps/ai_engine` consumes them. The AI engine reports lifecycle state and results through protected backend `/internal/ai/jobs/...` endpoints instead of importing backend modules or writing to Postgres directly. Real AI job bodies are not part of this version.

## Core Principles

- Capture is never blocked by patient selection.
- Patient assignment can happen later and can be changed by staff or processing.
- Generated/backend organization routes sessions to unassigned or needs-review queues; it does not mean human verified.
- `verified` means a doctor or assistant reviewed and accepted the generated session output.
- Generated placeholder outputs must be clearly marked so they can be replaced by real processing later.
- Tenant scoping is mandatory in the data model even while development uses one default tenant.

## Identity And Patient Model

Patients are first-class people who may become login-capable users later. A patient profile does not require a user account.

Core tables:

- `tenants`: clinic/account boundary.
- `users`: authenticated accounts for doctors, assistants, admins, and future patients.
- `tenant_memberships`: user role inside a tenant.
- `patients`: clinical patient profile inside a tenant.
- `patient_user_links`: optional link between a patient profile and a login-capable user.
- `patient_identifiers`: phone, email, external clinic ID, normalized names, birth date, and other matching identifiers.
- `audit_events`: immutable record of sensitive actions.

Roles:

- `doctor`: can capture, create patients, review, organize, verify, and reopen sessions.
- `assistant`: can capture, create patients, review, organize, verify, and reopen sessions unless restricted later.
- `admin`: can manage tenant configuration and users.
- `patient`: reserved for future patient-facing features and must not receive staff workflow permissions.

Patient rules:

- Doctors and assistants can create patients directly.
- Patient creation is tenant-scoped and audited.
- Duplicate detection may warn but must not block patient creation in v2.
- `sessions.patient_id` and `captures.patient_id` are nullable.
- Assignment and reassignment are audited with actor, previous value, next value, timestamp, and reason/source.

## Sessions

Core fields:

- `id`
- `tenant_id`
- `patient_id`, nullable
- `status`
- `title`
- `summary`
- `generated_summary`
- `generated_report`
- `extracted_metadata`
- derived response contracts: `report`, `summaries`, `findings`, `processingStatus`
- `organization_source`: `none`, `staff`, `ai-engine`
- `created_by_user_id`
- `review_started_by_user_id`
- `verified_by_user_id`
- `created_at`, `updated_at`, `captured_at`, `review_started_at`, `verified_at`

Session states:

- `unassigned`: default after upload when no patient is known.
- `needs_review`: session needs staff attention.
- `processing`: backend processing is in progress.
- `organized`: deprecated backend processing state; new processing routes to `unassigned` or `needs_review`.
- `reviewing`: doctor/assistant opened it for human verification.
- `verified`: doctor/assistant reviewed and accepted it.
- `reopened`: verified session was sent back for changes.
- `failed`: processing failed; source captures remain durable.

State rules:

- New uploaded sessions start as `draft` and are immediately reviewable.
- Captures can be appended in any state; appending a capture updates deterministic mocked progressive session contracts.
- The explicit save/processing endpoint is a report refresh hook, not a workflow gate.
- Successful processing moves sessions without patients to `unassigned`.
- Successful processing moves sessions with patients to `needs_review`.
- Opening a session for review moves it to `reviewing`.
- Staff verification can move any staff-visible session to `verified`.
- Reopen can move any staff-visible session to `reopened`.
- `organized` must never be treated as clinically verified.

Frontend contract rules:

- `report` is the stable report contract, with markdown body, status, source, timestamps, and stale flag.
- `summaries` is the stable summary contract, with short, clinical, and future patient-history fields.
- `findings` is a stable list of structured extracted finding rows.
- `processingStatus` is the stable user-facing processing contract and always includes `canEdit` and `canReview`.
- MVP migrations may reset local database and object-store data instead of preserving old session payload shapes.

Frontend grouping:

- Unassigned: `unassigned` sessions and sessions with unresolved routing.
- Needs review: `needs_review`, `reviewing`, `reopened`, and deprecated `organized` sessions requiring staff attention.
- Reviewed/Verified: `verified` sessions.

## Captures

Use a shared `captures` table plus type-specific metadata. Use JSONB with typed Pydantic schemas for v2; split into separate tables later only when querying requirements justify it.

Common fields:

- `id`
- `tenant_id`
- `session_id`
- `patient_id`, nullable
- `capture_type`: `audio`, `photo`, `note`
- `status`: `received`, `processing`, `processed`, `needs_attention`, `deleted`
- `source_artifact_id`
- `client_capture_id` for idempotent frontend retries
- `metadata` JSONB
- `captured_at`
- `created_by_user_id`
- `created_at`, `updated_at`

Idempotency:

- The frontend sends `client_capture_id` with every upload.
- Enforce a unique constraint on `(tenant_id, created_by_user_id, client_capture_id)`.
- If a retry repeats a completed upload, return the existing session/capture response instead of creating a duplicate.

Type metadata:

- Audio metadata: duration, codec, transcript text or artifact ID, transcript status, language, and generated marker.
- Photo metadata: width, height, OCR text or artifact ID, thumbnail artifact ID, image status, and generated marker.
- Note metadata: original text, normalized text, language, extraction status, and generated marker.

Generated metadata must include:

- `generated_by`: `ai-engine` for placeholder capture and session processors.
- `generated_at`
- `job_id`
- `confidence`, optional
- `source_artifact_ids`, optional

## Artifacts

Artifacts represent source files and generated outputs in MinIO.

Core fields:

- `id`
- `tenant_id`
- `capture_id`, nullable
- `session_id`, nullable
- `ai_job_id`, nullable
- `artifact_kind`: `source`, `transcript`, `ocr_text`, `thumbnail`, `summary`, `normalized_note`, `other`
- `bucket`
- `object_key`
- `mime_type`
- `byte_size`
- `checksum_sha256`
- `generated_by`, nullable
- `created_by_user_id`, nullable
- `created_at`

Object access:

- Do not expose permanent object keys as public URLs.
- File preview/download must go through backend authorization or short-lived presigned URLs generated after authorization.
- All artifact queries are tenant-scoped.

## API Shape

Auth:

```text
POST /api/v1/auth/dev-login
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/me
```

Patients:

```text
GET   /api/v1/patients?query=
POST  /api/v1/patients
GET   /api/v1/patients/{patient_id}
PATCH /api/v1/patients/{patient_id}
```

Sessions:

```text
GET   /api/v1/sessions?status=&limit=&cursor=
POST  /api/v1/sessions
GET   /api/v1/sessions/{session_id}
PATCH /api/v1/sessions/{session_id}
POST  /api/v1/sessions/{session_id}/assign-patient
POST  /api/v1/sessions/{session_id}/start-review
POST  /api/v1/sessions/{session_id}/verify
POST  /api/v1/sessions/{session_id}/reopen
GET   /api/v1/sessions/{session_id}/captures
GET   /api/v1/sessions/{session_id}/artifacts
GET   /api/v1/sessions/{session_id}/ai-jobs
```

Captures:

```text
POST  /api/v1/sessions/{session_id}/captures
GET   /api/v1/captures/{capture_id}
PATCH /api/v1/captures/{capture_id}
POST  /api/v1/captures/{capture_id}/assign-patient
GET   /api/v1/captures/{capture_id}/file
GET   /api/v1/captures/{capture_id}/metadata
POST  /api/v1/captures/{capture_id}/retry-processing
```

Processing:

```text
POST /api/v1/sessions/{session_id}/save
POST /api/v1/sessions/{session_id}/retry-processing
GET  /api/v1/ai-jobs/{job_id}
```

## Upload Flow

1. Frontend writes the source blob and metadata to IndexedDB.
2. Frontend creates or reuses a backend session.
3. Frontend uploads through `POST /sessions/{session_id}/captures`.
4. Backend validates auth, tenant membership, request size, MIME type, and session ownership.
5. Backend writes the source object to MinIO.
6. Backend creates the artifact, capture, and queued processing job records in Postgres.
7. Backend dispatches the capture processing task to Celery.
8. Backend returns stable backend IDs, current session state, processing job state, and authorized file URL information.
9. Frontend removes the pending outbox entry and may keep an evictable synced cache copy.

If object storage succeeds but the DB commit fails, the backend must clean up the object or mark it for orphan cleanup. It must not return success.

## Audit

Audit these events:

- dev login and production login/logout
- patient create/update
- capture upload
- artifact preview/download
- patient assignment/reassignment on sessions and captures
- AI processing enqueue/complete/fail
- session review start
- session verify
- session reopen

Audit rows include `tenant_id`, `actor_user_id`, target type/id, action, timestamp, request ID, and a small JSON details payload.

## Implementation Notes

- Use Alembic for migrations.
- Add Postgres, MinIO, Redis, and the `ai-engine` Celery worker to local and production Compose.
- Add an object storage abstraction so MinIO-specific code stays out of route handlers.
- Keep route handlers thin: auth dependency, service call, response mapping.
- Keep placeholder processing isolated behind service functions and Celery tasks that can be replaced by real AI logic later.
