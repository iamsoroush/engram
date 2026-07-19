# Synthesis Apply / User-State / Safety Correctness Hardening — Track E2 (2026-07-06)

The red-team of the synthesis apply + overlay + safety + user-state path (red-team process docs, since folded and pruned)
found a cluster of correctness bugs; the fixes below are load-bearing invariants future work must respect
(evidence + golden cases in that report; deterministic units in `tests/test_e2_synthesis_apply.py`):

- **`apply_active_patient_assignment` is the single choke point for a patient change.** It — not the
  per-endpoint code — drops the old patient's safety flags, syncs the new patient, and invalidates
  wrong-patient synthesis state (carry-forward confirmations + safety-reconcile decisions) on a true
  reassignment. This closes the AI-driven reassign path that never cleaned up the old patient, and fixes
  the capture-delete de-effect that passed the ORM `Session` (not `session.id`) so its `str()` matched no
  stored `sourceSessionId` (a silent no-op). A reassignment **force-re-synthesizes** against the corrected
  patient. The staff endpoint's now-redundant explicit drop/sync/escalate were removed.
- **The `report_version` cache is patient-scoped.** The capture-set hash is patient-blind, so a version is
  stamped with the `patientId` it was synthesized for and a cache-hit requires a match — a version made
  under a former patient never restores onto a reassigned session (its carry-forward doses + reconcile
  decisions belong to that other patient).
- **Freshness + version key come from the job-START capture-set snapshot** (INV-SNAPSHOT), not
  completion-time DB state — a mid-job fix-at-source edit leaves the report stale + dispatches a follow-up
  instead of stamping a stale report "current" or poisoning the version store.
- **A human treatment-overlay edit is never destroyed by a re-synthesis** (INV-IDENTITY-KEYS): the re-bind
  checks `priorKey == entry.treatmentKey` as a first-class rule (before the area filter, so an area re-slug
  can't break it) and **parks** an un-bindable edit in `treatment_overlay_orphans` (a review chip) instead
  of dropping it. `carried_forward_key` and safety-flag **rejections** are now rewording/language tolerant
  (anchored on `areaCode|norm(product)`; a rich `rejected_safety_flag_record` carries a rejection to a
  reworded flag).
- **`apply_safety_reconciliation` can never hide a distinct allergy:** an `ofKey` that doesn't resolve to a
  visible flag on THIS patient downgrades to keep, and mutual-duplicate cycles keep one canonical flag
  visible. A malformed synthesis is bounded-retried (transient) before falling back to the baseline; a
  hollow (all-empty-sections) output is treated as malformed; empty treatments over unchanged captures keep
  the prior rows + raise a review item. Completion/restore settle status **only from processing/draft** so a
  `reviewing` clinician isn't stomped. Metadata writers (completion handler + user-state endpoints) take a
  `SELECT … FOR UPDATE` row lock (INV-LOCK).
- **Meta-speech (administrative talk to staff / the app) is excluded from the report, summary, and patient
  memory** by an explicit prompt clause (synthesis `.v3`, patient-memory `.v2`), eval-gated with planted-meta
  cases in `report_sections_eval`.
