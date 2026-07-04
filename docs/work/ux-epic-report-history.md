# UX Epic — report version history (navigate, preview, restore)

**Status:** epic seed from the 2026-07-04 review — direction agreed with the user ("instead of the
ugly Undo button, a versioned history-like UI to navigate between report versions"), design not
started.

**Fold destinations (when built):** [`docs/ux/screens/capture.md`](../ux/screens/capture.md)
(report card + Sources drawer — replaces/augments the "Undo last capture" affordance),
[`docs/architecture/pipeline-versioning.md`](../architecture/pipeline-versioning.md) (status
updates), [`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md) (new AES band).

---

## 1. Why

The current undo surface is a single "Undo last capture" button in the Sources-drawer header —
functional but crude: one step, one direction, no visibility into what changed. Yet the substrate
underneath is already a full version store: `session_report_versions` records **every** synthesis
result, content-addressed by the ordered capture set, with a `pinned` column and a proven
restore path (`restore_report_version`, used by capture-undo today). The UI just doesn't expose it.

## 2. Design sketch (to be developed)

- **Entry:** a quiet `History` affordance on the report card (or Sources-drawer header, replacing
  the bare Undo button). Opens a version timeline.
- **Timeline:** one entry per stored version — time, trigger ("photo added", "capture removed",
  "transcript edited"), capture count; provenance (model/prompt version) available but demoted.
- **Preview (v1 core):** tapping a version renders it **read-only** in the report surface with a
  clear "viewing version from 14:32 — Back to current" banner. The user-state overlay
  (confirmations, rejected flags, treatment edits) applies on top of whichever version renders —
  user decisions are never time-traveled away.
- **Restore (the decision point):** two candidate semantics, to choose in design:
  1. **Restore = revert captures** — restoring an older version de-effects the captures added after
     it (the existing undo machinery, generalized to N steps). Destructive; owner-gated like undo.
  2. **Pin** — mark a preferred version as the rendered one without touching captures (the `pinned`
     column exists precisely for this). Non-destructive, but the pinned report and the capture set
     then disagree until the next synthesis — needs a visible "pinned — newer captures not
     reflected" state.
  v1 recommendation to evaluate: **preview + one-step restore (revert)** keeping today's semantics,
  with pin as a fast-follow.
- **Quick undo stays:** "Undo last capture" becomes a shortcut for "restore previous version" —
  same machinery, one tap.

## 3. Boundaries

- **Pro-first:** versions are synthesis artifacts; Basic's deterministic report rebuilds from
  captures and has no stored version chain (Basic keeps simple capture undo).
- No pipeline changes required: this epic consumes the existing store + overlay fold. (Confirmed
  against [ai-engine-refactor-plan.md](ai-engine-refactor-plan.md) — nothing new needed from the
  worker.)
- Version GC (pipeline-versioning D5, still pending) becomes user-visible once history is browsable
  — the bounded-ring decision should land with or before this epic.

## 4. Open questions

1. Restore semantics v1: revert-captures only, pin only, or both?
2. How far back does the timeline go (bounded ring size — ties to D5 GC)?
3. Should version diffs be shown (what changed between versions), or is trigger-labeling enough for v1?
4. Owner-only for restore (like undo today), or follow the tenant edit-policy presets?
