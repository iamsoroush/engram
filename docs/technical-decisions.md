# Technical Decisions

## Treatment-row actions consolidated; no theme-based UI for now (2026-07-08)

- **A treatment row has two actions, not three.** Correcting a field is the inline ✎ **Edit** (an
  instant human overlay — the treatment-overlay decision: never route a field correction through a
  re-synthesis); `↗ source` stays for traceability. The row's **"Fix at source" button was removed**
  — it duplicated the overlay path and contradicted that decision. `Fix at source` survives only on a
  coded review **note** with no editable row (low confidence / missing lot). Don't re-add it to rows.
- **Action chips are chrome → app language.** The `↗ source` citation now resolves via `t()`
  (`report.sourceCitation`), not the report's content language. Previously it followed
  `reportLanguage`, so a Persian report + English app showed "منبع" next to an English "Fix at
  source" on the same row.
- **No `prefers-color-scheme` in the app.** The only two dark-theme blocks (session patient strip +
  treatment editor, in `sessionSurface.css`) were removed so no section darkens alone on a
  dark-default browser. The app is single-theme (light) until a real theming pass is scoped.

## Batch-2 regression fixes — report-language default + technique-attribute whitelist (2026-07-08)

Two decisions from the Batch-2 production-regression pass that future agents must respect:

- **A tenant's `report_language` is seeded at sign-up, never left NULL.** `auth/service.register` now sets
  `report_language` from the sign-up language (mirrors `app_language`; `transcription_language` keeps its
  `"auto"` server default). A NULL `report_language` used to fall through to English section *titles* even
  while the AI wrote the *body* in the clinic's (Persian) language — a title/body language split. Defense in
  depth on the client: `LiveReport` resolves the section-title language as `report_language` → the report's
  own content script → `app_language` (never a bare English default). **Consequence:** a NULL
  `report_language` still means "follow the report-template default" for existing tenants, but new tenants
  are explicit; the client no longer assumes English when it is unset.
- **The treatment row renders a whitelist of genuine TECHNIQUE attributes only.** The synthesis attaches an
  open `attributes` map to each treatment; schema-v3 lets the model also drop STATUS / semantic keys there
  (e.g. `planned_vs_performed`) or coded uncertainties. `treatmentAttributeLines` now renders only known
  technique keys (needleGauge, depth, technique, plane, device, sessions, …) and drops everything else, so a
  status key can never leak as a raw `key · value` line — coded uncertainties keep flowing through the calm
  review-note path. **Consequence:** this is a **client-side** filter (no prompt/contract change, not
  eval-gated). If a genuinely new technique attribute needs surfacing, add its key to
  `TECHNIQUE_ATTRIBUTE_KEYS` in `captureModel.ts` rather than reverting to rendering every attribute.

## Session surface — layout diet + the deferred `edit` intent as a human overlay (2026-07-06)

The Batch-2 session-surface work made three shape decisions future agents must respect:

- **The report-`edit` intent ships as a human-authored overlay, not an AI intent.** The `edit` intent
  [intelligence-layer §1](intelligence-layer.md) deferred is realized (AES-1102..1105) as a **user-owned
  `treatment_overlay`** on top of the immutable AI artifact — the clinician types the truth directly; the
  AI is never asked to "apply an edit". This keeps the correction deterministic, instant, cost-free, and
  immune to re-mis-extraction. Rendered state stays `report_version ⊕ overlay`
  ([pipeline-versioning D2](architecture/pipeline-versioning.md)). **Consequence to respect:** never route
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

## Identity & Assignment Correctness — Never-Silent Lattice + Concurrency Invariants (2026-07-06)

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

## Synthesis Apply / User-State / Safety Correctness Hardening — Track E2 (2026-07-06)

The red-team of the synthesis apply + overlay + safety + user-state path (`docs/work/redteam/synthesis.md`)
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

## Cross-Visit Projection / Share / Lifecycle Invariants (Track E3) (2026-07-05)

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

## Patient Q&A hardening — honesty, isolation, abuse-resistance, harvest (2026-07-05)

Track-D+ red-team fixes on the post-session patient Q&A path ([aes-pro-qa-api.md](backend/aes-pro-qa-api.md)),
all on or near the send-to-patient path:

- **A voice edit that can't be applied fails visibly, never silently "Revised" (Q-1, INV-SILENT).** The
  gateway-less / unusable-output fallback echoes the current draft with a `mock-deterministic` source;
  the completion now treats a non-`ai:` source as a failure (`draft_status = failed_revise`, draft
  unchanged) and the UI only badges "Revised" when the draft carries a genuine `ai-voice:` source
  (`draftMode` set). The doctor is told the note didn't land instead of trusting an unchanged reply.
- **Draft ownership is an optimistic lock on `draft_job_id` (Q-2).** The inbox self-heal no longer
  dispatches over a `revising` draft, and every qa_draft/qa_revise completion writes only if the
  question still points at its job — a stale job that lost the race completes quietly, never clobbering
  a newer draft.
- **Cross-patient isolation is defence-in-depth (Q-3).** Prior answers (grounding comes from OTHER
  patients) have a leading greeting **name** stripped server-side, and the prompt's never-copy rule is
  now unconditional (renders even with zero exemplars) covering dose/product/brand/lot/date/name. Two
  new eval gate classes catch a copied cross-patient number and a leaked name.
- **State-change events invalidate dependent drafts (Q-5, INV-INVALIDATE).** Re-route, exemplar
  exclusion, and patient reassignment reset affected pending drafts to `none` so the self-heal
  re-drafts (new doctor's voice, without the excluded exemplar). Sent exchanges appended to
  patient memory are permanent by design (documented, not invalidated).
- **Terminal qa-job failure is a visible state (Q-7).** `fail_worker_job` marks the target question
  `failed` / `failed_revise` (was: stuck "drafting…" forever); the inbox polls pending drafts to land
  the state.
- **qa jobs are metered and pausable; the public ask is throttled (Q-8).** qa spend counts toward the
  fair-use budget and drafting **pauses** when over budget (the doctor can still reply by hand; the
  self-heal resumes when the budget frees). `/qa/{token}/ask` is rate-limited per thread with a
  concurrent-pending ceiling (`429`) so a leaked token can't flood the inbox or buy unbounded LLM calls.
- **Re-opening a revoked thread rotates its token (Q-9).** A revoked link was handed out to be dead;
  re-activation mints a fresh URL so the leaked one stays `404`.
- **The public Q&A page localizes to the clinic language + marks the deterministic fallback (Q-10).**
  The public payload carries `language`; the gateway-less starter draft is surfaced as "Starter reply —
  please review", not as a generated AI reply.
- **Doctor actions on a draft are harvested as eval signals (HALF-2).** A manual edit before send / a
  voice revise-replace is a `correction`, a dismiss is a `rejection`, recorded to `ai_feedback_events`
  as `ai_output_type = qa_reply` inside the same transaction (provenance in `context`; PII-scrubbed).

## Treatment Overlay + Synthesis Schema-v2 — Content-Anchored Keys, Not an LLM Id (2026-07-05)

The `edit` intent [intelligence-layer.md §1](intelligence-layer.md) deferred ships as a **human-authored
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
  `services/treatment_overlay.py`; see [pipeline-versioning D2](architecture/pipeline-versioning.md).
- **Correction-triggered synthesis escalation** (deferred from Wave 2): a user correction (fix-at-source
  edit, treatment-overlay edit, assignment reassignment) sets a pending marker that the next synthesis
  dispatch pops into an `escalate: true` job hint — the worker runs synthesis on the strongest configured
  tier (a correction is proof the cheap tier failed on this input). No-op when no escalation tier is set.

## Intelligence-Layer Simplification (2026-06-07)

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
  > dominant AI cost, **queue-collapse dispatched** (see the 2026-07-04 decision below) and
  > budget-gated. See [backend/processing.md](backend/processing.md) and
  > [business/ai-usage-limits.md](business/ai-usage-limits.md).
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

See [intelligence-layer.md](intelligence-layer.md) (contract) and [ai_engine/processing.md](ai_engine/processing.md).

## Encounter Chrome Noun Is Per-Vertical — "Visit" for Aesthetics (2026-07-04)

The clinical encounter's underlying object (and code) stays `session`, but the **chrome noun** the
clinician reads is chosen **per vertical**: aesthetics (and any non-therapy vertical) says **visit**
everywhere — the primary-nav label, the `+ New visit` button, visit titles, the `Visit:` time label;
therapy keeps **session**. `Shell` picks the primary-nav label by `tenant.vertical`
(`nav.activeVisit*` vs `nav.activeSession*`); all other chrome is plain catalog strings. This is
**chrome only** — clinical CONTENT is never touched — and future aesthetics surfaces must not coin
`session` chrome (extends the `glossary.*` terms; the surface note lives in
[ux/screens/capture.md](ux/screens/capture.md)).

## Synthesis Dispatch — Queue-Collapse, No Debounce (2026-07-04)

**Supersedes the quiet-period synthesis debounce.** An earlier design coalesced a visit's per-capture
synthesis runs with a time-window **debounce** (`synthesis_debounce_seconds`, default 0 = off, driven
by a trailing Celery-beat sweep). That setting, `session_synthesis_within_debounce`, and
`sweep_debounced_session_synthesis` are **removed**. Report synthesis (`session_organize`) is the
dominant AI cost (per-capture re-synthesis measured ~8.8× a coalesced run —
[business/ai-usage-limits.md](business/ai-usage-limits.md)); it is now cost-controlled with **no timer
and no added latency**:

- **Queue-collapse dispatch.** Single-flight per session + at most one pending job. The first capture
  synthesizes immediately; a trigger while a job is *queued* is a no-op (the queued job reads the full
  current capture set at `/start`), and a trigger while one is *running* yields exactly one collapsed
  follow-up (dispatched by the running job's completion handler). A **failed-but-retryable** job also
  counts as in-flight (`session_has_active_report_job`), so a capture arriving during the failure window
  merges into that job's recovery-beat retry instead of spawning a second job; a *terminal* failure does
  not block. A burst of N captures costs ≤ 2 runs instead of N. `force=True` (content edits / manual
  regenerate) keeps its meaning.
- **Cache-hit before dispatch.** Every settle first checks the content-addressed
  `session_report_versions` store for the current capture-set hash and **restores** deterministically
  instead of re-synthesizing (edit-then-revert, mark-relevant toggles, re-adds). Out-of-context
  membership is now part of the capture-set hash (pipeline-versioning **D1**), so a mark-relevant
  toggle is a correct hit/miss; the user-state overlay is re-applied on restore (ground-truth invariant).
- The debounce sweep is **repurposed** as `sweep_pending_session_synthesis` — a recovery-beat *catch-up*
  safety net (re-triggers a session left with an uncontributed capture and no active job), **not** a
  timer.

Worker and eval golden-set are unaffected (this changes *when/whether* synthesis runs, never its
inputs/outputs). See [backend/processing.md](backend/processing.md) "Pro report synthesis".

## One Router Module Per Domain — `main.py` Is Wiring-Only (2026-07-04)

The 1189-line `app/main.py` (81 inline handlers across ~14 domains) is dissolved: `main.py` is now
**wiring-only** (app construction + `/health` + `include_router`), and each domain is a
self-contained `APIRouter` in `app/<domain>_api.py` that delegates to `app/services/*`. This
finishes the pattern the `qa`/`insights`/`smart_lists`/`feedback` routers already set. Standing
convention: **new endpoints go in the matching domain router (or a new `<domain>_api.py`), never
inline in `main.py`.** Request/response models likewise live in per-domain `app/schemas/<domain>.py`
(`schemas/api.py` kept as a compat re-export aggregator). Behavior-preserving — the route surface
(paths, methods, tags, auth dependencies) is invariant, enforced by the new
`tests/test_route_surface.py` snapshot guard, and verified green through the e2e-stack P0 + p1-01
suites. Module map: [backend/README.md](backend/README.md) "Code layout".

## AI-Engine Pipeline Hardening — Contracts, Prompts, Structured Outputs, Escalation (2026-07-04)

The AI-engine refactor (Axis-1 increments 3–4 + Axis-2 §3.1/§3.2/§3.6) hardened the worker without
changing any AI job's intended outputs. Decisions:

- **Typed contracts stay worker-local.** Each job's output shaping moved from ad-hoc dicts to pydantic
  models under `ai_engine/contracts/`, one per payload family, each owning an `OUTPUT_VERSION`. The
  backend keeps validating its own side over JSON-HTTP; a shared contracts package would couple the two
  deployables the boundary keeps apart. A model must never silently tighten the old tolerance —
  enforced by old-vs-new parity tests on malformed inputs.
- **Prompt provenance is recorded, never keyed on.** Prompts moved to versioned `ai_engine/prompts/`
  modules (`PROMPT_VERSION` + `build`); every envelope stamps `schemaVersion` + `promptVersion`. A
  hash-pin test forbids silent wording changes. Per pipeline-versioning **D1**, cache keys still ignore
  prompt version.
- **Structured outputs on all JSON-emitting jobs.** `response_format=json_schema` on every JSON task
  (the gateway enforces it OpenAI-style for OpenAI + Gemini), with one validation-failure retry
  appending the error before today's fallback. Behind the `AI_ENGINE_STRUCTURED_OUTPUTS_ENABLED`
  kill-switch; the typed contract remains the validation layer (defense in depth). Streaming stays
  **rejected**.
- **Retry taxonomy is type-based.** Typed exceptions (`core/errors.py`) raised at the seam that knows
  the cause replace the substring matcher; new retryable reason code **`invalid_output`** separates
  model-output failures from gateway outages. Gateway-down stays retryable-then-durable; fair-use
  parking stays backend-owned.
- **Escalation tier is worker-side + config-driven.** Optional `{…, escalation:{model?, reasoningEffort?}}`
  per task, fired on the validation-failure retry (and on a backend `escalate: true` correction hint —
  the hint's *emission* is backend-owned and deferred to the overlay/Wave-3 work). No speculative
  cheap-first escalation.

Eval golden-sets are unaffected (behavior-preserving); the `processing.py` re-export shim is retained
for eval/test imports. See [ai_engine/processing.md](ai_engine/processing.md) and
[ai_engine/README.md](ai_engine/README.md).

## UX Docs Are The Current User-Facing Behavior Map

The compact docs under `docs/ux/` describe the currently implemented user-facing behavior. Future changes that alter screens, navigation, visible states, or workflows should update the relevant UX docs without duplicating backend API schemas.

## AI Engine Owns Capture Processing Execution

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based placeholder completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns execution of the capture processing jobs (initially deterministic placeholders, since replaced by the real gateway-backed pipeline — see [ai_engine/processing.md](ai_engine/processing.md)). The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.

## Continuously Evolving Session Contracts

Sessions are created as `draft` when the first capture reaches the backend, but the explicit save action is no longer the boundary for reviewability. A session can receive captures, be reviewed, and be edited across all states; completion is auto-derived (see "Intelligence-Layer Simplification").

Every backend session payload exposes stable frontend contracts for `report`, `summaries`, `findings`, and `processingStatus`. The contract shapes were designed so the real AI pipeline could replace the early mocked writer without changing frontend object shape — which is what happened; the real pipeline now fills them.

The backend still owns report template selection and can pass template content to the AI engine through the report refresh endpoint. Patient full name and national ID remain special extracted metadata fields because they anchor patient matching.

## Intelligence Layer Is Intent-Driven With An Explicit AI↔Backend↔Frontend Contract

Capture intelligence (assignment/reassignment, append, out-of-context) is being redesigned
from "AI extracts identity, backend decides silently" to an explicit, versioned contract:
the AI emits typed intents, the backend applies them with non-destructive, reversible,
capture-attributed semantics, and the frontend renders each capture's effect as a chip.
The `edit` intent and field-level provenance are deferred. Assignment reuses the existing
event-sourced `patient_assignment_timeline` (latest-valid-event-wins, undo by capture
deletion). Tiering (`basic`/`pro`) gates how much intelligence runs. `Patient` stays the universal
assignment target; the entity that generalizes across verticals is the *encounter*
(`Session` today; Study/Case in radiology/pathology), typed by `tenant.vertical`.

See [intelligence-layer.md](intelligence-layer.md) for the full v1 contract and open decisions.

## Structured Report Model Owns Report Content

The backend stores generated report body content in `sessions.report_model`, a JSON model with report sections, paragraph/image/artifact blocks, extracted findings, and source capture references. The active-session frontend renders clinic and patient information from non-AI template/session context, then renders backend-owned body markdown from the session report contract.

The singleton `default` report template is centralized in backend reporting code and currently exposes clinic context and body rendering rules. Patient information is injected from the assigned database patient and identifiers at render time; AI-generated body text must not be treated as the source of truth for patient demographics.

TODO: Add tenant-aware multi-template selection when Engram supports more than the default clinic report layout.

## Entity Model: Patient Universal, Encounter Generalizes By Vertical (A0)

`Patient` is first-class and **universal** across verticals and stays the assignment target — it
is **not** abstracted. The entity that generalizes is the report-required **Encounter**
(`Session` for clinics; `Study`/`Case` for radiology/pathology), one per `Report`. v1 implements
the Encounter as today's `Session` and does **not** rename it.

Implemented scaffolding (A0): `tenant.vertical` (default `aesthetics`; the legacy `clinic` value
is normalized to `aesthetics`) plus a reserved
`session.attributes` JSONB extension point for per-vertical fields (kept separate from
`extracted_metadata`). The work-unit presentation label is derived from the vertical via
`services/verticals.encounter_label` (aesthetics/therapy→"Session", radiology→"Study", pathology→"Case") and
surfaced on the `TenantProfile` (`vertical`, `encounterLabel`) — it must not be hardcoded in
core/apply logic. The literal `Session → Encounter` rename and the per-type `attributes` fields
land with the second vertical.

See [architecture.md](architecture.md) "Entity Model (verticals)" and
[intelligence-layer.md §2](intelligence-layer.md).

## Therapy Slice 1 — Changes Beyond The Original Plan (2026-06-14)

The therapy-vertical slice-1 build (`build/therapy-core`) is recorded in the therapy vertical
spec, tracked in the `docs/work/` process area. The plan was narrow: a
note-first capture surface + "Session so far" + a `vertical=='therapy'` report-synthesis branch + a
**minimal** client view (sessions list + per-session note/report) + federated caseloads, with backend
edits kept localized to `ai_jobs`. The following changes went **beyond that plan**; captured here so
future agents know what was added and why.

- **Frontend reuses the aesthetics design system, not a bespoke shell.** The therapy app renders
  inside the shared `Shell` (topbar/nav + the Note/Audio/Photo capture footer) and reuses the shared
  capture dialogs + `PatientForm`, mirroring the aesthetics `clinical-row` / `patient-history-card` /
  `workspace-report-card` markup. *Why:* the first cut was a parallel-universe UI; design-system
  consistency across verticals (reviewer feedback). The aesthetics `CaptureScreen` is still untouched.
- **Client creation in the therapy app** (RegisterPatientForm + duplicate guard). *Why:* the
  "minimal client view" had no create path, but a therapist must be able to add a client.
- **Full Note/Audio/Photo capture** via the shared footer (audio standardized to WAV through
  `audio.ts`), not note-only. *Why:* capture-first needs all capture types present (feedback); notes
  remain the primary, but audio/photo must work.
- **Client file shows longitudinal "Client history"** (the AI patient-memory summary + Story so far /
  Worth remembering / Right now) + a session timeline, beyond "sessions list + note/report". *Why:*
  longitudinal memory is the core therapy value and was the missing half of the client surface.
- **Federated-caseload scoping touches several shared read paths** (`patients`, `patient_search`,
  `patient_memory`, `sessions`) + a `caseload.py` helper — broader than the "localized to ai_jobs"
  constraint. *Why:* privacy (foundation §7 — a therapist sees only their own clients) is inherently
  cross-cutting across the patient/session read paths; it cannot live in one file. Aesthetics is
  unaffected (the scope is a no-op for shared-workspace verticals).
- **Therapy session-action endpoints** with request schemas —
  `/sessions/{id}/therapy/{format,release,risk,reflections}`. *Why:* the two-plane summary's controls
  (DAP/SOAP/BIRP switch, explicit Release, clinician-confirmed dated risk, private reflections) need
  persistence and thin routes.
- **Dev provisioning extras:** a therapy demo tenant, a 2nd therapist persona (`therapist-b`), and a
  widened `DevLoginRequest` (`tier=therapy`, `persona=therapist-b`). *Why:* to provision a therapy
  tenant to test against and to demonstrate federated caseloads with two clinicians side by side.
- **AI job prompts made vertical-agnostic** (`verticals.domain_descriptor` → passed into every job
  context; the AI engine reads it via `processing.domain_framing()` with a neutral "clinic" fallback;
  removed hardcoded "aesthetics clinic"/procedure vocabulary). *Why:* the capture/patient-memory
  prompts hardcoded aesthetics framing, so therapy tenants were told they were an aesthetics clinic.
  See the **caution** added to [ai_engine/README.md](ai_engine/README.md): jobs must not hardcode a
  vertical; extend the descriptor, never the prompts.
- **Durable screenshot tooling** (`apps/frontend/scripts/screenshot.mjs` + [dev/screenshots.md](dev/screenshots.md))
  driving the **system Chrome** (`channel:"chrome"`). *Why:* the Playwright browser-download CDN is
  blocked in the sandbox/CI; this lets any agent screenshot the running app with no download.
- **Therapy design prototypes realigned to aes-Pro** (`design-prototypes/therapy-*.html`). *Why:* the
  prototypes had drifted from the aesthetics design language (reviewer-requested follow-up).
- **Dev-only `.env` MinIO credential alignment** (not committed — gitignored). *Why:* the shared
  infra MinIO root creds drift/recreate (the documented flaky cred-mismatch), which 500s capture
  uploads; aligning the worktree's object-storage creds to the running MinIO unblocks verification.
- **AI model selection is NOT a user setting.** Models are chosen and optimized *centrally* by us
  (per-task, via `services/ai_model_config.py` live overrides + worker env defaults) — the whole cost
  model assumes specific models (cheap transcription + report model). The old user-facing "AI models"
  picker in Settings was removed; do **not** re-add a model picker to any user surface. *Why:* model
  choice is a cost/quality decision that must stay under our control, not the clinic's. The backend
  override API remains for our internal/admin use only. See
  [business/ai-usage-limits.md](business/ai-usage-limits.md).
- **Single-recording safety cap** (`MAX_RECORDING_SECONDS`, frontend `AudioDialog`): a live recording
  auto-stops + saves at 20 min so a mic left open can't burn a month of transcription budget in one
  clip. *Why:* the per-session capture-count cap and the monthly $ budget don't stop one runaway clip
  in the moment; auto-stop prevents the accident at the source. The clip captured so far is kept.
- **Fair-use $ budget is internal.** The per-seat AI budget (dollars) is never sent to the client or
  shown in the UI — only a percentage + status. `clinic_usage_state_dict` strips the dollar fields.
  *Why:* pricing/margin is internal economics, not something to surface to clinics.

## Report Sharing And Recall Decisions (2026-06-20)

Durable decisions from the Pro-report and recall builds:

- **One report, no separate patient projection.** The patient share is a curated subset of the
  *same* synthesized report — there is no second, patient-specific report artifact. Withholding is
  enforced server-side (only curated content is copied into the share snapshot), never by client
  filtering. See [ux/screens/patient-surface.md](ux/screens/patient-surface.md).
- **Share treatment specifics are generic by default.** A per-clinic `share_include_brands`
  setting (default **off**) controls whether shared treatment lines name brands; with it off the
  wording is generic. The structured treatment table and **lot numbers are always withheld** from
  patient shares regardless of the setting.
- **Assessment on the patient share is opt-in, default off.** Clinician findings can alarm out of
  context, so the assessment section is only shared deliberately per send.
- **Carried-forward dose gates completeness.** An unconfirmed carried-forward dose keeps a session
  out of `Complete` (`session_contracts.py:41`) — the one deliberate safety-critical exception to
  the warnings-over-blocking principle. Other review items (low-confidence, ambiguous, missing
  lot) stay non-blocking. See [ux/screens/session-review.md](ux/screens/session-review.md).
- **Lot-recall matching is exact-only.** Lot identity normalizes by uppercase + trim + collapse
  internal spaces, keeping hyphens/dots; near-misses are *never* merged into a recall cohort (a
  recall list must be trustworthy — fuzzy expansion belongs to a human, not the query).

## Matching Seam Runs on the Transcription Model — `m02` Near-Miss Stays a KnownGap (2026-07-04)

The patient-matching LLM seam (spoken-name extraction + assignment-intent) is **not a separate model**:
it is a by-product of audio transcription (`transcribe_audio_content` emits `patient_information` +
`intents`), so it runs on `AI_ENGINE_TRANSCRIPTION_MODEL` — live default **`gemini-3.1-flash-lite`**
([ai_engine/config.py](../apps/ai_engine/ai_engine/config.py)). The `m02` eval knownGap (a near-miss
surname «نگار معمری» intermittently auto-corrected to the existing patient «نگار محمدی») is a property
of **that** model class: measured 3× per model, flash-lite returned «محمدی» twice / «معمری» once and
`gemini-3.5-flash` also snapped to «محمدی», while `gemini-3.1-pro-preview` preserved a distinct name.

**Decision: keep transcription (and therefore the matching seam) on the flash-lite class; the `m02`
knownGap stays open, not retired.** Transcription runs on **every** capture — it is the highest-volume
AI call — so a pro-class model there is not cost-justified for the whole pipeline just to harden one
near-miss path. The deterministic backend gate is the real safety net (a fuzzy near-miss is **never**
silently auto-assigned regardless of the extracted string — `test_ai_assignment_gate.py`), so the
model's occasional auto-correction degrades a *candidate suggestion*, not patient safety. Retiring the
knownGap is deferred until the matching seam can take a **pro-class model independently** of bulk
transcription (a separate per-task model for the name-extraction path), at which point the eval's `m09`
noisy re-record proves the fix under load. Tracked in [ai_engine/evals.md](ai_engine/evals.md).

## Q&A Knowledge Retrieval — pgvector in the Existing Postgres; ChromaDB Rejected (2026-07-05)

The Q&A knowledge library (AES-410) grounds `qa_draft` in the clinic's own approved answers (curated
templates + auto-indexed sent replies) via hybrid lexical + embedding retrieval. Store decision:

- **pgvector inside the existing Postgres** — the `vector` extension + a `qa_knowledge_exemplars` table
  (alembic), **not** a dedicated vector DB. **ChromaDB was evaluated and rejected**: it is another
  always-on service to deploy, monitor, and back up on the single alpha VPS, with its own persistence
  and app-side multi-tenancy anyway. The corpus is tiny (hundreds–low-thousands of short texts per
  clinic) and retrieval needs SQL-side tenant/language/tag filtering + transactional writes with the
  owning rows — exactly what pgvector gives for free (existing backups/restore + tenant isolation
  included). Chroma wins only at scales this feature won't reach.
- **Operational cost of the choice — the Postgres image swaps `postgres:16-alpine` →
  `pgvector/pgvector:pg16`** (Debian-based) across `docker-compose.yml`, `docker-compose.shared-infra.yml`,
  and `docker-compose.prod.yml`. The extension is created per-database (`CREATE EXTENSION IF NOT EXISTS
  vector`), idempotent on the canonical DB, every dev-stack clone, e2e, and prod. **On an existing data
  volume the alpine(musl)→debian(glibc) collation provider changes**, so a one-time `REINDEX DATABASE`
  is required after the swap — recorded in [production-alpha-tradeoffs.md](production-alpha-tradeoffs.md).
- **Column is dimensionless `vector`** (exact in-memory scan over a tiny SQL-scoped candidate set — no
  ivfflat/hnsw index), so the schema is embedding-model-agnostic (a model swap needs no migration). A
  tiny custom SQLAlchemy `Vector` type (`app/db/pgvector.py`) binds/reads it as a `list[float]`, so **no
  `pgvector` Python dependency** is added. Tenant scoping is enforced in SQL; the lexical + embedding
  fusion (reciprocal of a term-cosine + an embedding cosine) is done in Python and unit-tested.
- **Backend embeds directly — the one place the backend calls an AI gateway.** Retrieval is
  backend-owned (the worker stays stateless), so the backend computes embeddings via an
  OpenAI-compatible `/embeddings` endpoint (`BACKEND_EMBEDDINGS_BASE_URL`, stdlib HTTP — no OpenAI SDK
  on the backend). Blank config ⇒ **lexical-only** deterministic retrieval, so dev/CI/e2e stay
  reproducible gateway-less. Secrets live in env only, like the worker's gateway config. The embedding
  cost is small + optional and is not yet metered through the worker's usage sink (alpha tradeoff).

See [backend/aes-pro-qa-api.md](backend/aes-pro-qa-api.md) and
[ai_engine/processing.md](ai_engine/processing.md) "Q&A draft".
