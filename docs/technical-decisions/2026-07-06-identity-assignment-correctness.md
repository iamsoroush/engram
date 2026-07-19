# Identity & Assignment Correctness — Never-Silent Lattice + Concurrency Invariants (2026-07-06)

Track E1 hardened the capture→patient-assignment pipeline (the incident cluster + red-team assignment
findings). The whole lattice now resolves in one place — `_resolve_capture_identity` in
`ai_jobs/worker.py` — under three structural invariants that are unit-tested, not per-bug patches:

- **INV-SILENT — no success-shaped silence.** A confident identity detection or an explicit instruction
  ends in exactly one of: an applied effect, a visible suggestion, or a visible "couldn't apply" notice.
  A completion-time backstop (`_explicit_instruction_unsatisfied`) plus a full decision-lattice unit
  suite (`tests/test_identity_assignment_lattice.py`) enforce it. New surfaced decision kinds:
  `suggested_name_correction` (Fix 1), `suggested_unassign` (A-F9 detach), `assignment_no_effect`
  (A-F12), `name_corrected` (explicit AI-patient rename), dead-zone create + `similarExisting` (Fix 7),
  and the `inertAssignment` conflict (A-F7).
- **INV-LOCK — serialize `session.extracted_metadata`.** Every capture completion holds
  `SELECT … FOR UPDATE` on the session row, and manual reprocess dispatch routes through the ordered
  `dispatch_next_session_capture` — so two completions can't interleave and clobber each other's
  append-only timeline event (A-F1/A-F2). FOR UPDATE is a dialect no-op on SQLite, so unit fakes are
  unaffected.
- **INV-INVALIDATE — state changes re-evaluate dependents.** An out-of-context capture (AI-flagged or
  staff-marked) is no longer a valid assignment basis — `active_patient_assignment_event` skips it, so
  marking OOC de-effects the assignment like deletion (A-F4); a fix-at-source transcript edit on the
  assignment-basis capture raises a `patient_recheck` chip (A-F6).

Other decisions: **name correction ≠ echo (Fix 1)** — an explicit correction of an AI-created
*unverified* patient renames in place (before→after harvested via the feedback helpers, `feedback.py`
untouched), otherwise a suggestion; **national-ID name cross-check (A-F5)** demotes an ID hit whose
spoken name is materially inconsistent (calibrated at 0.72 token-aware similarity) to `possible_match`;
**AI creation runs the AES-205 duplicate guard (A-F16)**; **reassigning away from an unreferenced
AI-created unverified patient archives it (Fix 6)** at the `apply_active_patient_assignment` chokepoint;
**recovery no longer flashes a session with an existing report back to `processing` (A-F10)**.
Transcription prompt bumped to `2026-07-05.transcription.v2` (explicit correction-directive
classification incl. «درستش», in-clip self-correction, OOC carve-out for assignment instructions, new
`detach` intent) — eval-gated with hermetic matching self-tests + committed `i0*` golden cases.
