# Cross-Visit Projection / Share / Lifecycle Invariants (Track E3) (2026-07-05)

The projection layer (patient memory, shares, worklist, insights) enforces two structural invariants
so a state change never leaves a stale/leaking projection behind:

- **INV-SNAPSHOT — memory freshness is stamped from the build-START inputs snapshot, never
  completion time.** The `patient_memory` worker freezes `updated_at` + the exact session-id set +
  the patient name when it *starts* the job (carried on `AiJob.result_metadata.memory_snapshot`) and
  writes those verbatim on completion (`built_from_sessions` / `built_from_name` on `patients.memory`).
  So a visit that changes *while the job runs* correctly leaves the memory stale, and staleness
  (`patient_memory_is_stale`) checks the SAME three signals: content-change time, **session-id-set
  change** (a reassignment/de-effect removes a visit whose remaining timestamps never move — the set
  is the only signal), and **rename**. This replaces the prior "stamp `updated_at = now` at
  completion" (which made removals/renames undetectable and races self-heal-proof).
- **INV-INVALIDATE — a patient change fans out to every projection that quoted the visit.**
  `apply_active_patient_assignment` (the one chokepoint shared by staff assign / AI assign /
  capture-delete de-effect) marks the **former** patient's memory `updating` and **auto-revokes**
  active shares of the visit; patient **archive** cancels waiting worklist entries and revokes both
  shares and Q&A threads.

Consequences and smaller fixes folded in:

- **The Pro memory read path never fabricates canned content.** The list/detail read only *de-spins*
  a stuck `updating` back to `ready`, preserving the prior AI memory and leaving `updated_at`
  untouched (so it stays stale and the AI rebuild is still due). The pre-AI mock's list-read finalize
  used to overwrite a real AI memory with deterministic "Memory spans N visits" text and stamp it
  fresh, silently destroying the longitudinal chain and suppressing the rebuild.
- **The patient name is never sent to the memory model** (shown beside the text; a rename must not
  strand a baked-in name). **Tier fail-closed:** an unknown/missing tier resolves to `basic`, and
  persisted summary/history are gated on the stored `mode` matching the current tier.
- **`effective_treatments` is the only treatments read on the two remaining bypass sites** (line-up
  `sinceLastVisit`, share "what we did"), and **lot/batch tokens are filtered out of AI-prefilled
  photo captions** server-side at share-snapshot time — extending the always-withhold contract to the
  caption channel. Public share media re-checks **patient ownership**, not just tenant.
- **Insights count only active patients** (one predicate, matching the panel / smart lists / memory
  list), removing the archived-patient discrepancy between tabs.
