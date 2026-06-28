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
**Foundation:** [pipeline-versioning.md](../architecture/pipeline-versioning.md) — undo is its first
consumer; the versioned `report_version` + user-state overlay defined there is the backbone for this doc.

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

> **Resolved (2026-06-28):** this ledger is the **`report_version`** of the
> [pipeline-versioning foundation](../architecture/pipeline-versioning.md), keyed by the **ordered
> in-context capture-version set** (model/prompt deliberately NOT in the key — D1). The immutable AI
> artifact is split from a mutable **user-state overlay** (confirmations / aftercare opt-outs /
> safety-flag rejections) so a restore never disturbs user decisions (D2). Undo builds on that store
> rather than defining its own; see the foundation for storage shape (D6) + retention/GC (D5).

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

> **Resolved (2026-06-28):** **soft-delete / deactivate** (reversible) the spurious AI-created patient
> when it has no other dependents; **never hard-delete**. If it has since acquired other
> captures/sessions, only **unassign this session** and warn.

## UX

### Affordance (Goal 1)

- **Just-captured Undo:** when a capture lands, a transient **"Capture added · Undo"** toast (a few
  seconds) that removes it — the fast path for "that transcription was wrong."
- **Per-capture remove ("Delete"):** the per-capture menu action — the **same operation** as Undo,
  applied to any capture. Undo and Delete are **one removal operation with identical effect**; "Undo" is
  just the accessible one-tap entry point for the **last** capture. (This means today's Delete is
  **upgraded** to de-effect properly — closing the original "deleted the capture but the patient stayed"
  bug.) Internally: last capture = cache-hit restore, middle capture = recompute — invisible to the user.
- Distinct copy from the safety-flag ✕ (that *rejects a flag*; this *removes a capture*). Confirm only the
  genuinely destructive branch (soft-deleting an AI-created patient).

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
- **One removal op, two entry points:** the existing capture-delete endpoint becomes the de-effecting
  `undo_capture` operation; "Undo" (one-tap, last capture) and "Delete" (menu, any capture) both call it.
- **Owner-only policy point:** gate removal at a single resolver — undo v1 default **owner-only**
  (`session.created_by_user_id == principal.user_id`), bypassing the normal role ladder (even admin).
  The tenant 3-mode edit policy (strict/standard/open) + non-owner-edit attribution markers are a
  fast-follow ([pipeline-versioning](../architecture/pipeline-versioning.md) §Permissions).
- **Preserve user state** (the recurring bug class): the user-state overlay (carried-forward
  confirmations, aftercare opt-outs, safety-flag rejections) is applied on top of the restored/recomputed
  version, never baked into it.
- **Patient projections recompute-from-source** (D4): after a removal, re-derive `Patient.safety_flags`
  (and mark patient memory stale) from the union of the patient's sessions' current kept flags — live +
  consistent, no drift. Cross-visit dedup/supersede is the [safety-reconcile job](../architecture/pipeline-versioning.md)
  (D7, selection-only over the user-clean set); a removal itself is a deterministic filter (no LLM).

## Phased plan

Built on the [pipeline-versioning foundation](../architecture/pipeline-versioning.md) (its phase 1 = the
version+identity layer + user-state overlay). Undo proper:

1. **Restore (last-capture undo)** — cache-hit restore of the prior `report_version` (deterministic) +
   gating (Goal 5).
2. **Patient-action revert** — soft-delete a spurious AI-created patient when safe / else unassign;
   owner-only policy point. Closes the motivating case.
3. **Middle-capture recompute** + patient-projection recompute-from-source (D4) + patient-memory
   staleness propagation (D3) + the quick UX (one-tap last-capture Undo + upgraded per-capture Delete,
   reachable without opening Sources).
4. **Feedback harvest** — a mis-transcription that created a patient is a **transcription** eval case
   (`kind=correction`, `ai_output_type=transcript`). Plus, per the eval-gating rule, the synthesis
   caching/restore must keep `apps/ai_engine/eval/run_all.py` green (+ targeted determinism cases).

## Decisions (resolved 2026-06-28)

1. **Storage:** the [`report_version`](../architecture/pipeline-versioning.md) store — keyed by the
   ordered in-context capture-version set; **not** a parallel ledger, **not** model/prompt-keyed (manual
   re-run is the escape hatch for model changes). Immutable AI artifact + separate user-state overlay.
2. **Spurious AI patient on undo:** soft-delete when no other dependents; else unassign + warn. Never
   hard-delete.
3. **Middle-capture undo:** **recompute** (one LLM pass), shown as a non-blocking "re-organizing…" state
   — safe because the clinical records are versioned, not regenerated from nothing.
4. **Undo window:** **any processed capture**, anytime (while gating holds). Removal is **owner-only**
   (even admin can't) via a single policy point; the tenant 3-mode policy (strict/standard/open) + its
   UI + non-owner-edit attribution are a fast-follow.
5. **Undo = Delete:** one removal operation with **identical effect**; "Undo" is the one-tap shortcut for
   the last capture. Today's Delete is upgraded to de-effect properly.

## Remaining open questions

- `report_version` home — table vs normalized `processed_versions` extension (see foundation §Open
  questions); settle once the overlay shape is fixed.
- Capture-version retention depth (every transcription edit vs current+last) — affects GC ring sizing.
