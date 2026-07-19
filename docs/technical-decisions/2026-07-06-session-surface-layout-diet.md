# Session surface — layout diet + the deferred `edit` intent as a human overlay (2026-07-06)

The Batch-2 session-surface work made three shape decisions future agents must respect:

- **The report-`edit` intent ships as a human-authored overlay, not an AI intent.** The `edit` intent
  [intelligence-layer §1](../intelligence-layer.md) deferred is realized (AES-1102..1105) as a **user-owned
  `treatment_overlay`** on top of the immutable AI artifact — the clinician types the truth directly; the
  AI is never asked to "apply an edit". This keeps the correction deterministic, instant, cost-free, and
  immune to re-mis-extraction. Rendered state stays `report_version ⊕ overlay`
  ([pipeline-versioning D2](../architecture/pipeline-versioning.md)). **Consequence to respect:** never route
  a treatment-field correction through a re-synthesis; it is an overlay write.
- **Provenance subline and reconcile banner are one surface.** The backend overlay entry exposes a single
  `{aiValue, value}` pair (no edit-time vs post-synthesis distinction), so the UI unifies Q3's "dictated"
  provenance and §3.3's Keep-yours/Use-AI reconcile into **one never-silent affordance** (the AI value is
  always visible; one tap adopts it; Keep-yours is the default). A distinct "AI *now* reads X" banner would
  need a new backend signal (edit-time dictation kept separately) — deliberately not added in v1.
- **The patient strip is the session-screen shell.** Identity + session context + verify state + safety
  collapse into one sticky line above the report (nine zones → strip → report). Safety is never buried (a
  red chip when collapsed; a `high_risk_clinic` tenant setting pins the full panel open); active conflicts
  stay in a thin always-visible band; history auto-surfaces on (re)assignment. **Consequence to respect:**
  new above-the-report chrome belongs *inside* the strip's expansion, not as a new stacked zone.
