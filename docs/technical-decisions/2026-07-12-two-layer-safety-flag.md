# Two-layer safety flag: normalized label + verbatim evidence (2026-07-12)

Owner testing found the safety panel legible only after reading a full dictated sentence. Shipped as
AES-2001/AES-2002 (stories in [aesthetics-stories.md](../ux/aesthetics-stories.md); UX in
[capture.md](../ux/screens/capture.md)). Decisions worth recording:

- **The flag carries two clinical layers, not one.** Synthesis now emits a per-flag **`label`** — a
  normalized short clinical label (kind + substance, report language, native script) — *alongside* the
  unchanged verbatim `text`. The UI shows the label as the legible primary and the verbatim sentence as
  expandable evidence. The verbatim-quote rule is untouched (still "quote the clinician"); the label is
  additive. This is an eval-gated synthesis change: PROMPT_VERSION bumped to `2026-07-12.synthesis.v18`
  (pinned hash updated in the same commit) and `safety_flags_eval` gained label assertions (normalized,
  no verbatim-sentence echo, native script), re-verified at `EVAL_VOTES=3`.
- **`label` is additive — the output contract version was NOT bumped.** `SafetyFlag.label` is optional
  (`None` when absent), so a pre-label stored/streamed output still parses and the client falls back to
  the verbatim `text`. `SESSION_SYNTHESIS_OUTPUT_VERSION` stays `…v3` deliberately so the backend
  `is_synthesis` gate keeps matching; only the shape widened. The contract-parity goldens were
  regenerated (a deliberate act) to record the new field.
- **Reconcile/rejection keys stay text-based.** The label is passthrough only. The stable
  `safety_flag_key` (and the reconcile `newFlags` inputs) still key on `kind|normalized-text`, so a
  reworded label never shifts a rejection or a cross-visit reconcile decision. Label rides onto the
  patient store + cross-visit payload purely for display.
- **Safety expansion is event-driven, reusing the pin-open machinery.** The patient strip auto-expands
  when the kept-flag signature changes to a new, unacknowledged set (first assignment of a patient with
  flags, a flag landing from synthesis/reconcile, a restore/undo), and records an **acknowledged
  signature** in session UI state so a collapse is not undone for the same set. The collapsed strip
  always shows a red `🩹 N` count chip.
