# Architecture

## Product Shape

Engram is capture-first clinical memory. The primary workflow is:

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
  Prometheus /metrics + GlitchTip error tracking

AI Engine
  Celery worker (+ beat) process
  Gateway-backed AI jobs: transcription, image caption,
  report synthesis, patient memory, Q&A drafts

Storage
  Postgres metadata
  MinIO object storage (development and production)
```

Postgres is the source of truth for tenants, users, patients, sessions, captures, artifacts, audit events, and processing job rows; the schema is managed with Alembic. MinIO stores source files and generated artifacts in both development and production. See [backend data model](backend/data-model.md), [storage](backend/storage.md), [auth](backend/auth.md), and [production](production.md) for details.

Celery and Redis provide the background job boundary. The backend creates durable job rows and sends named tasks; `apps/ai_engine` consumes them and executes the AI jobs against an LLM gateway ([ai_engine/processing.md](ai_engine/processing.md)). Every AI job is **eval-gated**: changes must keep `apps/ai_engine/eval/run_all.py` green ([ai_engine/evals.md](ai_engine/evals.md)).

The AI engine does not import backend modules or connect directly to Postgres. It updates job lifecycle state and results through protected backend internal endpoints at `/internal/ai/...`. This keeps the backend as the owner of database schema, tenant scoping, audit events, and capture/job state while allowing the AI engine to evolve as a separate service.

The one narrow exception is **Q&A knowledge retrieval** (AES-410): retrieval is a backend concern (the worker stays stateless), so the backend makes a single optional outbound call to an OpenAI-compatible `/embeddings` gateway to embed the query + exemplars for hybrid retrieval (`app/services/qa_knowledge/`). Unconfigured (`BACKEND_EMBEDDINGS_*` blank) it degrades to deterministic lexical-only retrieval, so dev/CI/e2e are unaffected. Embeddings are stored in a pgvector column in the existing Postgres — no new datastore.

## Data Flow

### Capture

1. User records audio, takes/selects a photo, or writes a note.
2. Browser writes the source blob into IndexedDB before attempting network upload.
3. UI confirms local safety using the shared UX state language.
4. The outbox attempts upload to the backend when possible.
5. Backend stores the source file and session metadata.
6. On an AI-capable tenant, the backend creates a queued capture processing job and dispatches it to Celery (in per-session capture order). On aesthetics Basic — zero AI capabilities — no job is created; the report rebuilds synchronously.
7. Browser removes the pending outbox entry and keeps a synced local cache copy.
8. The worker transcribes/captions the capture through the gateway and reports start/complete/fail back to the backend; failures retry with bounded backoff and are swept by the recovery beat.
9. UI updates through assistant-style states owned by [UX states](ux/states.md).

### Session Evolution And Report Generation

The first uploaded capture creates a durable backend session. Sessions are continuously evolving objects: new captures can be added in any state, and every session response includes frontend-stable `report`, `summaries`, `findings`, and `processingStatus` contracts.

Report generation is two-layered (details: [backend/processing.md](backend/processing.md)):

- **Deterministic baseline (always, both tiers, no LLM):** once a session's capture chain is idle, the backend rebuilds the live report synchronously as a pure function of the processed, in-context captures — grouped by type for Pro, chronological for Basic. The report is always current; the session settles to `needs_review` (patient assigned) or `unassigned`. Completion is auto-derived (`complete`) — there is no manual verify step.
- **Pro LLM synthesis (the revived `session_organize` job):** for synthesis-enabled Pro tenants, a single-pass LLM job then refines the baseline into the synthesized report — prose plus structured treatments, safety flags, and aftercare selections. It runs as a quiet enrichment (the baseline stays visible), is debounced over a quiet period so a visit's captures coalesce into ~one run, and is the dominant AI cost — its dispatch is gated by the fair-use budget ([business/ai-usage-limits.md](business/ai-usage-limits.md)).

Structured report content is stored in `sessions.report_model` as the backend source of truth; markdown remains a rendered/export format. The default singleton report template renders clinic information, patient information, and body sections; patient information is injected from the assigned patient record and identifiers, not from AI-generated body text.

Each synthesis output is snapshotted as a content-addressed report version, so capture undo/delete restores a previously-seen state deterministically (no LLM, no "wrong entries") with user decisions preserved — see [architecture/pipeline-versioning.md](architecture/pipeline-versioning.md).

### Review

When previewing a capture, the frontend resolves the source in this order:

1. Pending local source from IndexedDB, if the capture has not synced.
2. Synced browser cache, if present.
3. Backend source file URL.

This keeps review fast while still allowing cache eviction after backend sync.

## AI Layer

The real, gateway-backed AI pipeline (worker execution: [ai_engine/processing.md](ai_engine/processing.md); backend orchestration: [backend/processing.md](backend/processing.md)):

- **Per-capture jobs** — transcription (audio), neutral image caption (photo), plus patient matching/intent and out-of-context detection.
- **Report synthesis** (`session_organize`) — the Pro single-pass synthesis above, including the **safety-reconcile** pass (cross-visit safety-flag dedup/supersede; selection-only, never generation).
- **Patient memory** — the Pro cross-visit summary + history projection; lazy (read/line-up triggered plus a background quiescence sweep), never enqueued per-session.
- **Patient Q&A drafts** (`qa_draft` / `qa_revise`) — AI-drafted, doctor-verified replies on the patient Q&A surface ([backend/aes-pro-qa-api.md](backend/aes-pro-qa-api.md)).

Cross-cutting machinery:

- **Tier gating by capability** — features gate on `(vertical, tier)`-resolved capabilities (`services/capabilities.py`); aesthetics Basic resolves to zero AI ([spines.md](spines.md) §3).
- **Fair-use metering/limits** — real gateway spend is metered per clinic/seat/month; over budget, background enrichment jobs park and resume next period. Capture is never blocked. See [business/ai-usage-limits.md](business/ai-usage-limits.md).
- **Recovery** — a Celery-beat sweep re-dispatches due queued/failed/stale jobs, resumes parked jobs, drives the debounced synthesis, and refreshes quiescent stale patient memory.
- **Safety flags** — synthesis-detected flags project to the patient as the recomputed union of kept flags; rejections are user-authoritative, deterministic, and instant.

## Product Surfaces (backend-served)

- **Patient shares + public surface** — tokenized, revocable curated snapshots (`/share/{token}`) and the Pro patient Q&A (`/qa/{token}`); the token is the capability, withholding is structural. Contracts: [backend/aes-basic-api.md](backend/aes-basic-api.md), [backend/aes-pro-qa-api.md](backend/aes-pro-qa-api.md).
- **Smart lists + lot/product recall** — deterministic Pro lists over synthesized treatments, plus the exact-match recall cohort ([ux/screens/patients.md](ux/screens/patients.md)).
- **Insights** — owner/admin clinic analytics (deterministic aggregation; treatments tab Pro-gated) — [backend/insights-feedback.md](backend/insights-feedback.md).
- **AI-quality feedback harvester** — staff corrections/ratings of AI outputs recorded as candidate eval cases (same doc).

## Observability

The backend exposes Prometheus metrics at `/metrics` (HTTP metrics plus product-critical counters such as failed capture uploads and AI-job failures) and ships errors to self-hosted GlitchTip via the Sentry SDK with PHI-scrubbing `before_send` hooks (`app/observability/`). The full overlay (Prometheus/Grafana, exporters, Uptime Kuma, alert rules): [monitoring.md](monitoring.md).

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

- There is no encryption-at-rest implementation yet.
- Browser storage quotas are not fully surfaced to the user yet.
- Audio recording on phone browsers may require HTTPS; a file input fallback exists for local HTTP testing.
