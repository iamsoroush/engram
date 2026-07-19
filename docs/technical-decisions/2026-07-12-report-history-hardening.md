# Report-history hardening: redo, safety-loss guard, soft-delete-only (2026-07-12)

Three owner-testing findings on the E17 report-history feature drove three decisions (stories
AES-1709/1710/1711; mechanics in [architecture/pipeline-versioning.md](../architecture/pipeline-versioning.md)):

- **Restore is a full transition (redo), not one-way removal.** A version's reachability is now computed
  over the session's captures *including soft-deleted rows*, so restoring **forward** **re-effects**
  (un-deletes) the captures a target version knew — later versions stay navigable after a restore. The
  earlier "removal-only, forward versions become preview-only" behaviour was the bug. The forward branch is
  pruned from the timeline (`pruned_at` column — row kept, UI hidden) **only** when a new capture is added
  while behind head, behind a client confirm gated on `session.forwardVersionCount`. Restoring to a
  non-linear (out-of-context-toggle) version stays preview-only / `409`.
- **A rollback must never *silently* drop safety content.** Restore and Sources-drawer undo/delete now
  compute a **deterministic (no-LLM) safety-loss diff** from the two states' artifacts and confirm first,
  naming the flags that disappear — including the patient-layer effect (invalidated vs. stays because
  another visit sources it). We deliberately did **not** route this through an LLM: the diff is a pure
  function of the versioned artifacts, so it is instant, free, and auditable. A no-safety-loss removal is
  **not** interrupted (quick undo stays one-tap).
- **De-effect is soft-delete-only; media is never destroyed.** Undo / restore only set
  `CaptureStatus.deleted` (+ remember the pre-delete status for re-effect) — never touch the `Artifact`
  row or its MinIO object. This is what makes redo possible and is asserted + regression-tested (a
  de-effected audio capture's media stays fetchable internally).
