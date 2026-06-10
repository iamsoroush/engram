# Technical Decisions

## Intelligence-Layer Simplification (2026-06-07)

A product-direction simplification of the intelligence layer:

- **Patient matching is tier-neutral.** Intelligent matching (match/suggest/reassign/create) runs
  for **both** Basic and Pro — it is the core memory-accuracy feature. Tier now gates only
  **enrichment** (image captions + note decoration, Pro only) and the **report layout**.
- **Report generation is deterministic — no LLM, no async job.** The `session_organize` Celery
  dispatch was replaced by a synchronous `regenerate_session_report` built from the session's
  processed, in-context captures (Basic = one chronological section; Pro = grouped-by-type:
  Audio notes / Written notes / Photos). Always current for the latest capture; no "updating" churn.
  The legacy worker session path is retained only to drain in-flight jobs.
- **Completion is auto-derived, not manually verified.** The manual *Verify report* gate
  (`/sessions/{id}/verify` + `/reopen`, the report button, `SessionStatus.verified`) is removed. A
  session's **`complete`** flag is computed (`session_is_complete`: captures processed + patient
  assigned + report current/not-stale) and surfaced on the session payload + the patient-memory
  `complete` indicator. The `verified` enum value is retained only for historical rows.
- **Basic photos carry no AI caption.** Un-enriched photos write a blank caption; the UI offers a
  manual "Add caption" instead of a placeholder.
- **Per-task models.** Transcription / caption / note-decoration each take an env-configured model
  (`AI_ENGINE_{TRANSCRIPTION,CAPTION,NOTE_DECORATION}_MODEL`, optional `*_BASE_URL`/`*_API_KEY`;
  blank = fall back to the transcription gateway).

See [intelligence-layer.md](intelligence-layer.md) (contract), [ai_engine/processing.md](ai_engine/processing.md),
and the "Simplification pass" entry in [intelligence-layer-stories.md](intelligence-layer-stories.md).

## UX Docs Are The Current User-Facing Behavior Map

The compact docs under `docs/ux/` describe the currently implemented user-facing behavior. Future changes that alter screens, navigation, visible states, or workflows should update the relevant UX docs without duplicating backend API schemas.

## AI Engine Owns Capture Processing Execution

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based placeholder completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns deterministic placeholders for audio, text, and image capture processing. The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.

## Continuously Evolving Session Contracts

Sessions are created as `draft` when the first capture reaches the backend, but the explicit save action is no longer the boundary for reviewability. A session can receive captures, be reviewed, and be edited across all states; completion is auto-derived (see "Intelligence-Layer Simplification").

Every backend session payload exposes stable frontend contracts for `report`, `summaries`, `findings`, and `processingStatus`. Phase 2.1 writes deterministic mocked outputs into those contracts so the real AI pipeline can later replace the mock writer without changing frontend object shape.

The backend still owns report template selection and can pass template content to the AI engine through the report refresh endpoint. Patient full name and national ID remain special extracted metadata fields because they support deterministic placeholder matching now and future patient matching later.

## Intelligence Layer Is Intent-Driven With An Explicit AI↔Backend↔Frontend Contract

Capture intelligence (assignment/reassignment, append, out-of-context) is being redesigned
from "AI extracts identity, backend decides silently" to an explicit, versioned contract:
the AI emits typed intents, the backend applies them with non-destructive, reversible,
capture-attributed semantics, and the frontend renders each capture's effect as a chip.
The `edit` intent and field-level provenance are deferred. Assignment reuses the existing
event-sourced `patient_assignment_timeline` (latest-valid-event-wins, undo by capture
deletion). Tiering (`basic`/`pro`) gates how much intelligence runs. `Patient` stays the universal
assignment target; the entity that generalizes across verticals is the *encounter*
(`Session` today; Study/Case in radiology/pathology), typed by `tenant.vertical`.

See [intelligence-layer.md](intelligence-layer.md) for the full v1 contract and open decisions.

## Structured Report Model Owns Report Content

The backend stores generated report body content in `sessions.report_model`, a JSON model with report sections, paragraph/image/artifact blocks, extracted findings, and source capture references. The active-session frontend renders clinic and patient information from non-AI template/session context, then renders backend-owned body markdown from the session report contract.

The singleton `default` report template is centralized in backend reporting code and currently exposes clinic context and body rendering rules. Patient information is injected from the assigned database patient and identifiers at render time; AI-generated body text must not be treated as the source of truth for patient demographics.

TODO: Add tenant-aware multi-template selection when Memora supports more than the default clinic report layout.

## Entity Model: Patient Universal, Encounter Generalizes By Vertical (A0)

`Patient` is first-class and **universal** across verticals and stays the assignment target — it
is **not** abstracted. The entity that generalizes is the report-required **Encounter**
(`Session` for clinics; `Study`/`Case` for radiology/pathology), one per `Report`. v1 implements
the Encounter as today's `Session` and does **not** rename it.

Implemented scaffolding (A0): `tenant.vertical` (default `clinic`) plus a reserved
`session.attributes` JSONB extension point for per-vertical fields (kept separate from
`extracted_metadata`). The work-unit presentation label is derived from the vertical via
`services/verticals.encounter_label` (clinic→"Session", radiology→"Study", pathology→"Case") and
surfaced on the `TenantProfile` (`vertical`, `encounterLabel`) — it must not be hardcoded in
core/apply logic. The literal `Session → Encounter` rename and the per-type `attributes` fields
land with the second vertical.

See [architecture.md](architecture.md) "Entity Model (verticals)" and
[intelligence-layer.md §2](intelligence-layer.md).
