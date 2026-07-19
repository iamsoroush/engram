# Treatment Overlay + Synthesis Schema-v2 — Content-Anchored Keys, Not an LLM Id (2026-07-05)

The `edit` intent [intelligence-layer.md §1](../intelligence-layer.md) deferred ships as a **human-authored
overlay, not an AI intent** — a clinician types the truth directly; the AI is never asked to "apply an
edit" (keeps it deterministic, instant, cost-free, immune to re-mis-extraction). Decisions:

- **Stable treatment identity is a deterministic, backend-computed, content-anchored `treatmentKey`, not
  an LLM-emitted opaque id.** Independent synthesis runs have no memory, so an emitted id could only be
  stable by echoing prior ids — failing exactly on the hard split/merge case — whereas a content anchor
  (`t|<areaCode|norm(area)>|norm(product)|<first sourceCaptureId>`, Unicode-general `norm`, ordinal on
  collision) is reproducible by construction; the same pattern the safety `flag_key` proved. The model's
  `priorKey` echo is a re-bind **tie-breaker only**, never authoritative.
- **Synthesis output bumps to `session-synthesis-output.v2`** (both the ai_engine contract and the
  lockstep backend copy the worker gates on): treatments gain canonical English `areaCode` (language-
  independent key anchor, selected from `domain.areaCodes` so `prompts/` stays vertical-agnostic) +
  `priorKey`; a BCP-47 `lang` stamp lands on the synthesis envelope + treatments + safety flags AND the
  other jobs' envelopes (caption/memory/transcription) — worker-stamped, additive; and free-string
  `uncertainties` gain a machine-readable `uncertaintyReasons` companion. One eval-gated migration
  (treatments key-echo-stability case added).
- **`treatment_overlay` is the fourth `OVERLAY_METADATA_KEYS` class** — folded at render/projection via a
  single `effective_treatments()` (the ONLY treatments any projection reads, so a corrected lot/dose is
  authoritative for recall / lot-recall / smart lists / patient-memory — the safety case), re-bound after
  each synthesis with a **no-LLM `{aiValue, value}` reconcile diff** (never a silent overwrite), and
  excluded from restore. A carried-forward dose edit auto-satisfies the confirm blocker (epic Q4). v1 is
  owner-gated field-edit only; the editing UI is a later epic. Mechanics live in
  `services/treatment_overlay.py`; see [pipeline-versioning D2](../architecture/pipeline-versioning.md).
- **Correction-triggered synthesis escalation** (deferred from Wave 2): a user correction (fix-at-source
  edit, treatment-overlay edit, assignment reassignment) sets a pending marker that the next synthesis
  dispatch pops into an `escalate: true` job hint — the worker runs synthesis on the strongest configured
  tier (a correction is proof the cheap tier failed on this input). No-op when no escalation tier is set.
