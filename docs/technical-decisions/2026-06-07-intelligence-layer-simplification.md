# Intelligence-Layer Simplification (2026-06-07)

A product-direction simplification of the intelligence layer:

- **Patient matching is tier-neutral.** Intelligent matching (match/suggest/reassign/create) runs
  for **both** Basic and Pro — it is the core memory-accuracy feature. Tier now gates only
  **enrichment** (image captions + note decoration, Pro only) and the **report layout**.
- **Report generation is deterministic — no LLM, no async job.** The `session_organize` Celery
  dispatch was replaced by a synchronous `regenerate_session_report` built from the session's
  processed, in-context captures (Basic = one chronological section; Pro = grouped-by-type:
  Audio notes / Written notes / Photos). Always current for the latest capture; no "updating" churn.
  The legacy worker session path is retained only to drain in-flight jobs.
  > **Superseded (partially):** the deterministic rebuild still stands as the always-current
  > baseline, but `session_organize` was later revived as the **Pro single-pass LLM report
  > synthesis** (prose + treatments + safety flags + aftercare) that refines the baseline — the
  > dominant AI cost, **queue-collapse dispatched** (see [Synthesis Dispatch — Queue-Collapse](2026-07-04-synthesis-dispatch-queue-collapse.md)) and
  > budget-gated. See [backend/processing.md](../backend/processing.md) and
  > [business/ai-usage-limits.md](../business/ai-usage-limits.md).
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

See [intelligence-layer.md](../intelligence-layer.md) (contract) and [ai_engine/processing.md](../ai_engine/processing.md).
