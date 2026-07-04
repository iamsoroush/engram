# Backend Data Model

As-built data model of the FastAPI backend: Postgres for metadata (Alembic-managed), MinIO for
source files and generated artifacts, backend-managed JWT auth, and tenant-scoped services.
All tables live in `apps/backend/app/models.py` — that file is the source of truth; this doc is
the map. API contracts live in the OpenAPI schema (`/api/v1/openapi.json`) plus the two
human contract docs ([aes-basic-api.md](aes-basic-api.md), [aes-pro-qa-api.md](aes-pro-qa-api.md)).
Auth and object storage have their own docs ([auth.md](auth.md), [storage.md](storage.md)); AI-job
orchestration is in [processing.md](processing.md).

## Core Principles

- Capture is never blocked by patient selection; assignment can happen later (staff or AI).
- A capture is only "safely transferred" after the MinIO object **and** its Postgres metadata are
  both committed.
- Tenant scoping is mandatory: every tenant-owned query filters by the authenticated `tenant_id`.
- Session completion is auto-derived, never a manual gate.
- Generated (AI) metadata is always marked with `generated_by`, `generated_at`, and `job_id`.

## Identity And Tenancy

- `tenants` — the clinic/account boundary. Carries the product configuration:
  `tier` (`basic` | `pro`), `vertical` (`aesthetics` | `therapy` | … — see
  [architecture.md](../architecture.md) "Entity Model"), language preferences
  (`transcription_language`, `report_language`, `app_language`), `match_strictness`,
  `qa_routing_mode`, `share_include_brands`, and `role_permissions` (the multi-seat presets).
- `users` — authenticated accounts (staff and future patients). Unique email; password hash for
  production login.
- `tenant_memberships` — a user's role inside a tenant (`MembershipRole`): `owner` (the founding
  user from sign-up — a full superset of doctor + admin), `doctor`, `assistant`, `admin`,
  `patient` (reserved). Membership `status` (`active`/`disabled`/`invited`) is re-checked live on
  every request (see [auth.md](auth.md)).
- `auth_refresh_tokens` — hashed refresh tokens with revocation.
- `app_config` — global (non-tenant) runtime key/value config; powers live per-task AI model
  selection (internal-only — not a user setting).

## Patients

Patients are first-class people who may become login-capable users later; a profile does not
require an account.

- `patients` — the clinical profile: display/legal names, DOB, sex, phone, email, notes, plus two
  AI-maintained JSONB projections: `memory` (the Pro patient summary+history) and `safety_flags`
  (the cross-visit union of kept flags — see [processing.md](processing.md)).
- `patient_identifiers` — matching identifiers (national ID, phone, email, normalized/alias names,
  …) with normalized values, source, and confidence; feeds smart search, the duplicate guard, and
  AI patient matching.
- `patient_user_links` — optional link between a patient profile and a login-capable user.

Rules: staff create patients directly (tenant-scoped, audited); duplicate detection warns but
never blocks; `sessions.patient_id` and `captures.patient_id` are nullable; assignment and
reassignment are audited with actor, previous/next value, and source.

## Sessions

`sessions` is the vertical-generic *encounter* (see the entity model in
[architecture.md](../architecture.md)). Key fields:

- `patient_id` (nullable), `status`, `title`, `summary`
- `report_model` (JSONB) — the structured report body (sections, paragraph/image blocks, source
  capture references); the backend source of truth for report content. `generated_report` holds
  the rendered markdown; `generated_summary` the summary text.
- `extracted_metadata` (JSONB) — AI/processing output **and** the user-state overlay: synthesized
  treatments, safety flags, aftercare selections, `report_synthesis` state, plus the
  user-authoritative overlay keys (`rejected_safety_flags`, `confirmed_carried_forward`,
  `dismissed_aftercare`) that a version restore never overwrites (see
  [pipeline-versioning](../architecture/pipeline-versioning.md)).
- `attributes` (JSONB) — reserved per-vertical extension point (empty for capture-first verticals).
- `report_template_key`, `organization_source` (`none` | `staff` | `ai-engine`)
- attribution + timestamps: `created_by_user_id` (the owner in the multi-seat model),
  `created_at`, `updated_at`, `captured_at`.

### Session status semantics

`SessionStatus`: `draft`, `unassigned`, `needs_review`, `processing`, `organized` (deprecated),
`reviewing`, `verified` (enum-only, historical), `reopened`, `failed`.

- The first uploaded capture creates the session; captures can be appended in any state.
- After processing, a session settles to `needs_review` (patient assigned) or `unassigned` (no
  patient). States describe attention, not access — sessions stay editable and reviewable in
  every state.
- **Completion is auto-derived**, not manually verified: `session_is_complete` (captures
  processed + patient assigned + report current) is computed and surfaced on the session payload.
  The manual verify/reopen routes were removed (2026-06-07); the `verified` enum value is
  retained only for historical rows and is never set. `organized` is likewise legacy-only.

User-facing labels and grouping are owned by [UX states](../ux/states.md).

## Captures

One shared `captures` table plus type-specific JSONB metadata (typed via Pydantic schemas).

- `capture_type`: `audio` | `photo` | `note`
- `status`: `received`, `processing`, `processed`, `needs_attention`, `deleted`
- `source_artifact_id`, `client_capture_id`, `metadata` (JSONB), `captured_at`,
  `created_by_user_id`

Type metadata holds the generated output for each type — `transcript` (audio), `caption` (photo),
`detail` (note; notes are a pure passthrough) — plus per-capture processing effects
(`ai_processing`, `report_contribution`, patient-match/intent results). Generated entries carry
`generated_by`, `generated_at`, `job_id`, and optional confidence/source references.

### Idempotency

The frontend sends `client_capture_id` with every upload; a unique constraint on
`(tenant_id, created_by_user_id, client_capture_id)` makes retries idempotent — a repeated
completed upload returns the existing session/capture response instead of creating a duplicate.

## Artifacts

`artifacts` maps Postgres metadata to MinIO objects (source files and generated outputs):
`artifact_kind` (`source`, `transcript`, `ocr_text`, `thumbnail`, `summary`, `normalized_note`,
`other`), `bucket` + `object_key` (unique pair), MIME type, byte size, SHA-256 checksum, owning
capture/session/AI job, and `generated_by`.

The database is the authority for ownership and authorization; MinIO is the binary store. Object
keys never expose patient names; file access goes through backend authorization or short-lived
presigned URLs (details in [storage.md](storage.md)).

## AI Jobs

`ai_jobs` is the durable record of background AI work (see [processing.md](processing.md) for
dispatch, ordering, recovery, and fair-use gating).

- `job_type` (`AiJobType`): the per-capture jobs (`audio_capture_process`,
  `text_capture_process`, `image_capture_process`), `session_organize` (the Pro report
  synthesis), `patient_memory` (patient-scoped Pro summary+history), and the patient-Q&A jobs
  `qa_draft` / `qa_revise` (patient-scoped; their target message rides in `result_metadata`).
- `status` (`AiJobStatus`): `queued`, `running`, `succeeded`, `failed` (plus legacy `completed`).
- Scope: exactly one of `capture_id` (capture jobs), `session_id` without capture (synthesis), or
  `patient_id` (patient-scoped jobs).
- Durable retry state: `attempt_count`, `last_dispatched_at`, `next_retry_at`, `retry_reason`,
  `last_error` — recovery re-dispatches from these rows, so queued/failed work survives worker
  and broker restarts.

`ai_usage_counters` accumulates real gateway spend and volume per `(tenant, user, period_key)` —
the fair-use meter's source of truth (cost in micro-dollars; monthly `YYYY-MM` UTC periods). See
[docs/business/ai-usage-limits.md](../business/ai-usage-limits.md).

## Report Versions

`session_report_versions` — immutable, content-addressed snapshots of a session's synthesized
report + structured artifacts, keyed by `capture_set_hash` (hash of the ordered in-context
capture versions). An undo that returns a session to a previously-seen capture set restores the
stored version deterministically (no LLM). `pinned` rows are exempt from future GC. The
user-state overlay is *not* stored here. Full design:
[pipeline-versioning](../architecture/pipeline-versioning.md).

## Feature Tables

- `aftercare_templates` — per-procedure deterministic aftercare templates (AES-702).
- `patient_shares` — tokenized, revocable curated patient shares; the share snapshots curated
  content at create time (the structural withholding contract — see
  [aes-basic-api.md](aes-basic-api.md)).
- `qa_threads` / `qa_messages` — the Pro post-session patient↔clinic Q&A
  ([aes-pro-qa-api.md](aes-pro-qa-api.md)). A `qa_messages` patient question carries the AI draft +
  its `draft_provenance` (the top retrieved exemplar the draft was grounded in — doctor-only).
- `qa_knowledge_exemplars` — the Pro Q&A **knowledge library** (AES-410): curated `template`s +
  auto-indexed `sent_reply`s, the retrieval corpus behind grounded `qa_draft`. Per-tenant; a
  normalized `search_text` (lexical match target) + an optional native pgvector `embedding` (NULL when
  the embeddings gateway is unconfigured → lexical-only). `status` `active`/`excluded` is the
  manage/exclude list; `source_message_id` links an indexed reply back to its `qa_messages` row
  (idempotent auto-index). Requires the `vector` extension (see
  [technical-decisions.md](../technical-decisions.md) → *Q&A Knowledge Retrieval*).
- `worklist_entries` — the soft "line a patient up" lane (AES-903).
- `ai_feedback_events` — harvested AI-quality signals (corrections/confirmations/ratings) feeding
  the eval golden sets; see [insights-feedback.md](insights-feedback.md).

## Upload Safety

The backend does not report upload success until the MinIO object, the artifact row, and the
capture row are all durable. The upload path writes the object first, then commits the Postgres
rows; on any failure it rolls back the transaction and best-effort deletes the just-written
object (no orphan claims of success). Failed uploads increment the
`engram_capture_uploads_failed_total` metric (capture-first is product-critical). See
[storage.md](storage.md) for the storage-side requirements.

## Audit Trail

`audit_events` is the immutable record of sensitive actions: `tenant_id`, `actor_user_id`, target
type/id, `action`, request ID, and a small JSON details payload. Audited domains include auth
(login/logout/refresh/register/switch-tenant), patient create/update/assignment, capture
upload/update/delete, artifact preview/download, AI processing enqueue/complete/fail, session
edits and report decisions (safety-flag rejection, carried-forward confirmation, aftercare
dismissal), patient shares, Q&A actions, team/plan management, and worklist changes. The
canonical list is the `action="…"` call sites in `apps/backend/app`.
