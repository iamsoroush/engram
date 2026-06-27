# Capture undo + versioned per-capture effects

> **Goal.** A wrong capture (most often a mis-transcription — e.g. «بیمار باردار است» heard as
> «بیمار بردیا رست است», which then makes the AI *create a new patient*) must be **undoable in one tap**,
> and the undo must **revert that capture's effects** — not just drop it from the feed. Today, deleting a
> capture removes it and re-runs the pipeline, but it does **not** de-effect it (the spuriously created/
> assigned patient stays). This redesign makes each capture's effects **attributable + versioned**, so an
> undo restores the exact prior state deterministically instead of re-generating (which risks new, wrong
> entries), and only re-runs the pipeline when it genuinely must.

Companion: [capture.md](screens/capture.md), [redesign-capture-surface.md](redesign-capture-surface.md),
[redesign-session-context.md](redesign-session-context.md), `docs/ai_engine/capture-intelligence-design.md`.

## Current state (the gap)

- **Delete ≠ de-effect.** `onDeleteCapture` removes the capture and marks the report stale → a
  re-synthesis recomputes treatments/report from the remaining captures. But a capture's **patient
  action** (AI create/assign, recorded in `extracted_metadata.patient_assignment_timeline` +
  `ai_patient_action`) is **not** reverted, so a patient created from a garbled name persists.
- **Re-generate, not restore.** Re-synthesis is an LLM call — deleting the *last* capture and re-running
  can yield *different* prose/treatments than the pre-capture state ("wrong entries"). There's a
  session-level snapshot ring (`extracted_metadata.processed_versions`, last 5, written in
  `services/ai_jobs/worker.py`), but it is **not** used as an undo source and is keyed by synthesis run,
  not by capture.
- **Effects are only partially attributable.** `treatments[]` and `safety_flags[]` already carry
  `sourceCaptureIds`; the report blocks, the patient action, aftercare selections, and the summary do
  **not** carry per-capture provenance — so "remove just this capture's contribution" isn't expressible.
- **Undo is buried.** The only way to drop a capture is the per-capture overflow menu inside the Sources
  drawer. There is no quick, prominent undo, and no rule for *when* undo is safe.

## Goals (from the owner)

1. **One-tap undo of a capture, without opening Sources** — a quick affordance (a just-captured "Undo"
   toast + an undo on the capture chip), not hidden in a menu.
2. **De-effect on undo:** reverting a capture reverts *its* effects — the patient it created/assigned,
   its treatments, its safety flags, its report contribution.
3. **Saved + versioned per-capture effects:** fetch a prior version deterministically; **do not
   re-generate on undo** — *unless* a **middle** capture is removed, in which case the pipeline runs.
4. **Versioned artifacts per capture** (treatments / allergies / etc.) so the correct version is fetched
   **without wrong entries**. Design this carefully — it is the backbone.
5. **Undo gating:** undo is enabled **only when** all captures are processed **and** the report is
   complete + up-to-date (no in-flight synthesis / pending capture jobs) — so the version being restored
   is coherent and the undo target is unambiguous.

## Design — capture-effects model

### A capture's effects (the unit of undo)

Every capture, once processed, contributes a bounded, enumerable set of **effects**:

| Effect | Where it lives today | Per-capture attributable today? |
|---|---|---|
| **Patient action** (AI create / assign / match from spoken identity) | `extracted_metadata.patient_assignment_timeline`, `ai_patient_action`; the created `Patient` row | the timeline event carries `capture_id` — partial |
| **Treatments** | `extracted_metadata.treatments[]` | **yes** — `sourceCaptureIds` |
| **Safety flags** | `extracted_metadata.safety_flags[]` (+ `Patient.safety_flags`) | **yes** — `sourceCaptureIds` |
| **Aftercare selections** | `extracted_metadata.aftercare_selections[]` | derived from treatments (indirect) |
| **Report blocks / summary** | `report_model.sections[].blocks[]`, `summary` | **no** — holistic synthesis output |
| **The capture's own text** | `capture_metadata.transcript/caption/detail` | n/a (belongs to the capture) |

### The versioned artifact store (the backbone — Goal 4)

Introduce a **per-session capture-effects ledger**: an append-only, versioned record mapping each
**synthesis version** → the **capture set** it was computed from → the **structured artifacts** it
produced (treatments, safety flags, aftercare, summary, report-model id), each tagged with the
`sourceCaptureIds` that justify it.

- Each synthesis run already replaces the live artifacts and snapshots the prior ones into
  `processed_versions`. Formalize that into a typed **`capture_effects` version entry**:
  `{ versionId, capturedCaptureIds: [...], artifacts: { treatments, safetyFlags, aftercareSelections,
  summary, reportModelRef }, patientActionRef, generatedAt }`.
- **Determinism:** because each version stores the *exact* artifacts (not a prompt), restoring a version
  is byte-stable — no LLM, no "wrong entries". This is what makes undo trustworthy.
- **Attribution:** because every structured artifact carries `sourceCaptureIds`, "this capture's
  contribution" is computable: an artifact whose `sourceCaptureIds` ⊆ {undone capture} is removed; one
  shared with surviving captures is kept (or recomputed — see below).

> Decision needed (Q1): store the ledger in `extracted_metadata.capture_effects` (JSONB, simplest,
> rides the existing snapshot machinery) **or** a dedicated `session_capture_versions` table (cleaner
> queries, provenance, no metadata bloat). Recommendation: a **table**, given this is auditable
> version history and metadata is already heavy.

### Undo strategy — restore vs recompute

Let the undone capture be **C**, the ordered processed set be `[…]`.

1. **C is the latest effecting capture** (the common case — undo right after capturing): **restore** the
   immediately-prior `capture_effects` version. Pure data swap, no synthesis. Deterministic, instant.
   This directly satisfies "saved + versioned, not re-generated."
2. **C is a middle capture** (later captures' effects may depend on / interleave with C, e.g. a
   correction/supersede chain): there is no prior version that equals "all captures except C", so
   **recompute** — drop C and run the pipeline over the remaining captures. Flagged to the clinician as a
   re-organize (it's an LLM pass; may differ).
3. **C had no synthesis effect yet** (still processing, or consult-only): just remove the capture +
   revert its patient action (if any); no version work.

"Latest vs middle" is decided from the ledger: C is *latest-effecting* if no surviving capture has an
artifact that supersedes/【depends-on】C and C is the last in `capturedCaptureIds` order. Otherwise middle.

### Reverting the patient action (the motivating case)

If C's effect set includes a **patient action** (`patient_assignment_timeline` event with
`capture_id == C` and `action ∈ {ai_created, ai_assigned, manually_assigned}`):

- **AI-created patient, not yet confirmed, no other captures/sessions reference it** → **delete /
  deactivate** the spurious `Patient` (it only existed because of the bad transcription). Reuse
  `dismissAiPatientAction` + a guarded patient cleanup (only when the patient has no other dependents).
- **Assigned an existing patient** → **unassign** the session (revert to the prior assignment state from
  the timeline), don't touch the patient.
- Always pop the timeline event so the assignment chip/state reflects the revert.

> Decision needed (Q2): deleting an AI-created patient is destructive. Recommendation: **soft-delete /
> deactivate** (reversible) when safe, never hard-delete; if the patient has acquired other
> captures/sessions since, only unassign this session and warn.

## UX

### Affordance (Goal 1)

- **Just-captured Undo:** when a capture lands, a transient **"Capture added · Undo"** toast (a few
  seconds) that removes it — the fast path for "that transcription was wrong."
- **Per-capture Undo:** an inline **Undo/✕** on the capture chip (Sources drawer *and* a compact chip row
  surfaced above the report so it's reachable without opening Sources).
- Distinct copy from the safety-flag ✕ (that *rejects a flag*; this *removes a capture*). Confirm only the
  genuinely destructive branch (deleting an AI-created patient).

### Gating (Goal 5)

Undo is **enabled only when**: no capture is still uploading/processing **and** no synthesis/report job
is in flight **and** the report is current (not stale). Reuse the existing guards
(`session_has_pending_capture_jobs`, `session_has_active_report_job`, the `generated_output_stale` flag).
While disabled, show why ("Finishing up this capture…"). This guarantees the restored version is coherent.

## Backend shape (sketch)

- **Ledger:** `session_capture_versions` (or `extracted_metadata.capture_effects`) written on every
  synthesis completion in `services/ai_jobs/worker.py` (extend the existing `processed_versions` write).
- **`undo_capture(session, capture)` service:** classify latest/middle/no-effect → restore prior version
  **or** dispatch re-synthesis; revert the patient action; soft-delete a spurious AI patient when safe;
  emit an `ai_feedback_events` row (a mis-transcription that created a patient is a **transcription**
  failure signal — eval-epic §1b — `kind=correction`, `ai_output_type=transcript`, before=garbled,
  after=removed).
- **Endpoint:** `POST /sessions/{id}/captures/{captureId}/undo` (distinct from plain delete, which stays).
- **Preserve user state across the recompute path** (the bug class we keep hitting): carry forward
  `confirmed_carried_forward`, `dismissed_aftercare`, `rejected_safety_flags` exactly as the safety/
  aftercare work does.

## Phased plan

1. **Ledger + restore (latest-capture undo), no patient revert** — formalize versioned artifacts; undo
   the last capture by restoring the prior version (deterministic). Gating in place.
2. **Patient-action revert** — revert AI create/assign on undo (soft-delete spurious patient when safe).
   This closes the motivating case.
3. **Middle-capture recompute path** + the quick UX affordances (toast + chip undo outside Sources).
4. **Feedback harvest** — log mis-transcription-that-created-a-patient as a transcription eval case.

## Open questions (for the owner)

1. **Ledger storage:** dedicated table vs `extracted_metadata.capture_effects`? (rec: table)
2. **Spurious AI patient on undo:** soft-delete when safe vs always-just-unassign? (rec: soft-delete when no other dependents)
3. **Middle-capture undo:** recompute silently, or require an explicit "re-organize" confirm (since it's a non-deterministic LLM pass)?
4. **Undo window:** undo any processed capture anytime (while gating holds), or only the most-recent N / within a time window?
5. **Relationship to plain delete:** does "Delete" stay as a separate (non-reverting) action, or does undo replace it entirely?
