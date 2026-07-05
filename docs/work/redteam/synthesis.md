# Red-team report: report-synthesis pipeline (apply · overlay · safety · user-state)

> Verbatim agent report, 2026-07-05. Scope: `ai_engine` synthesis job + safety reconcile → backend apply (`worker.py`, `reports.py`, `report_versions.py`, `treatment_overlay.py`, `patient_safety.py`, `sessions.py`, `session_processing.py`, `captures.py`) → capture UI (`CaptureScreen.tsx`, `LiveReport.tsx`, `captureModel.ts`). Ranked by severity.

## S-F1 — Safety flags stay on the WRONG patient after AI reassignment; capture-delete drop is a no-op bug
**T6 · CRITICAL · CONFIRMED-IN-CODE**

Three reassignment paths exist; only one cleans up the old patient's safety store:

- **Manual assign endpoint** — correct: `sessions.py:573-578` calls `drop_session_safety_flags(old_patient, session.id)` then syncs the new patient.
- **AI-driven reassignment** (auto-applied spoken reassignment): `worker.py:539-545` → `assign_session_to_ai_patient` → `apply_active_patient_assignment` (`patient_assignment_timeline.py:169-…`) — **no safety-flag handling anywhere on this path**. The old (wrong) patient keeps this visit's allergy/contraindication flags forever.
- **Capture-delete de-effect** — `captures.py:283` passes the ORM object: `drop_session_safety_flags(former_patient, session)`. `drop_session_safety_flags` does `str(session_id)` (`patient_safety.py:124`), producing `"<app.models.Session object at 0x…>"` — never equals a stored `sourceSessionId`, so **the filter removes nothing**. The intended de-effect is silently dead; `sessions.py:576` correctly passes `session.id`, proving the intended contract.

**Production symptom:** patient W permanently shows "allergy to lidocaine" contributed by a visit that was later refiled to patient R.

**Fix direction:** move drop+sync into `apply_active_patient_assignment` itself (the single place `session.patient_id` changes), diffing old→new patient; fix `captures.py:283` to pass `session.id`. **Golden case:** session with kept flags assigned to W → AI-reassign to R → assert `W.safety_flags` has no entry with `sourceSessionId == session.id` and `R.safety_flags` does; repeat via capture-delete reversion.

## S-F2 — Wrong-patient history contaminates carry-forward and survives reassignment (no re-synthesis on reassign)
**T6/T2 · HIGH · CONFIRMED-IN-CODE**

`bounded_prior_visit_treatments` (`session_processing.py:330-352`) feeds the assigned patient's last-visit treatments into the prompt; "same as last time" copies that dose. If the session was mis-assigned to patient W when synthesis ran:

1. The carried dose is **W's** dose, cited to **W's** prior capture (allowed by `prior_visit_capture_ids`, worker.py:907).
2. Reassignment to R only calls `mark_synthesis_escalation` (`sessions.py:582`) — **never dispatches a re-synthesis**. All captures are already `added`, so `session_has_uncontributed_capture` is False and the sweep (`reports.py:474-507`) never re-triggers. The wrong-patient dose persists indefinitely under R.
3. If the clinician confirmed the dose before reassignment, `confirmed_carried_forward` (keyed `area|product`, patient-agnostic) survives — the wrong dose now reads **confirmed** under R, and `session_is_complete` (`session_contracts.py:44-55`) reports Complete.
4. Mid-job variant (T8): reassignment while the job runs → at completion `prior_ids` is recomputed from **R** (worker.py:907) so the carried row's W-sourced citations are stripped (`process_synthesized_treatments`, session_processing.py:412-416) — the row survives with empty sources while its content is still W's.

**Fix direction:** on reassignment, force-dispatch synthesis (pair the existing escalation marker with `regenerate_session_report_if_idle(force=True)`), or at minimum invalidate carried-forward rows + their confirmations. **Golden case:** W has prior 20u botox; session mis-assigned to W; dictate "same as last time"; reassign to R (prior 30u) → assert a fresh synthesis is dispatched and the 20u carried row does not survive.

## S-F3 — One malformed/refused LLM response permanently kills Pro extraction for the visit; zero-treatments output is indistinguishable from a no-treatment visit
**T1 · HIGH · CONFIRMED-IN-CODE**

- Malformed content (refusal, prose, truncated JSON, missing summary) → `parse_session_synthesis_output` returns None (`contracts/synthesis.py:317-331`) → skip sentinel (`jobs/session_synthesis.py:690-692`) — **not an exception, so never retried**. The backend skip handler (`worker.py:801-855`) marks every reportable capture `added` and the job `succeeded`. Result: no treatments, no safety flags, no aftercare for the visit — permanently, unless content later changes. A transient bad completion silently downgrades a Pro visit to Basic with no operator signal (`synthesis_skip_reason` buried in `result_metadata`).
- Separately, a *successful* parse with `treatments: []` for a visit that clearly performed treatments is accepted verbatim: the only gate is a non-empty `summary` (`contracts/synthesis.py:329-331`). The store is overwritten to `[]` with no review item and no distinction from a genuine consult-only visit.

**Fix direction:** (a) bounded retry for `empty_or_malformed_synthesis` (it is exactly as transient as a network error); (b) when fresh treatments are empty but `previous_metadata["treatments"]` was non-empty (same capture set), raise a review item / keep prior store flagged stale. **Golden case:** completion with `treatments: []` over a session whose prior synthesis had 3 rows and unchanged captures → assert rows are not silently dropped; malformed body → assert a retry is scheduled, not a contributed skip.

## S-F4 — One re-synthesis can permanently destroy human treatment-overlay edits (incl. corrected lot numbers)
**T4/T6 · HIGH · CONFIRMED-IN-CODE**

`rebind_treatment_overlay` (`treatment_overlay.py:225-271`) drops any entry whose fresh row can't be found, and `worker.py:1033` **omits the `treatment_overlay` key entirely when the rebound list is empty** — the drop is unrecoverable (entries aren't retained anywhere; `_ARTIFACT_METADATA_KEYS` excludes overlay by design, `report_versions.py:38-43`).

Two drop vectors the model controls: (1) a `treatments: []` run (S-F3) drops every overlay entry in one pass; (2) **area-anchor drift** — `_rebind_candidate` requires `_treatment_area_anchor(row) == entry["matchArea"]` *before* `priorKey` is consulted (`treatment_overlay.py:262-271`). A re-synthesis that re-slugs `areaCode` ("cheeks" → "left-cheek") breaks the anchor; **a row explicitly echoing `priorKey == entry.treatmentKey` is still not considered** because it fails the area filter — the priorKey hint, built precisely for this, cannot rescue the binding.

Safety-critical consumer: `effective_treatments` feeds lot-recall cohorts — a clinician-corrected lot silently reverts to the wrong AI lot after any re-synthesis that re-keys the row.

**Fix direction:** check `priorKey == entry.treatmentKey` as a first-class re-bind rule (before/independent of the area filter); park un-bindable entries in a `treatment_overlay_orphans` list surfaced as a review chip instead of deleting them. **Golden case:** overlay lot edit on `t|cheeks|ژل|<cap>`; re-synthesize with the same row emitting `areaCode: "left-cheek"` + `priorKey: "t|cheeks|ژل|<cap>"` → assert the edit re-binds; re-synthesize with `treatments: []` → assert the edit is parked, not destroyed.

## S-F5 — Mid-job capture edit poisons both the freshness signature and the version store
**T8 · HIGH · CONFIRMED-IN-CODE**

`complete_session_worker_job` computes the content signature and the version's capture-set hash from the **DB state at completion time**, while the artifacts reflect the **payload at job start** (`worker.py:905-906`, `worker.py:1055-1066`, `worker.py:1083` → `record_report_version` → `session_capture_set`, `report_versions.py:67-96`).

Scenario: synthesis running; clinician does a fix-at-source transcript edit. The edit's own dispatch is a no-op (`session_has_active_report_job`, `reports.py:443`). At completion: (1) the stale report is stamped "current" **for the post-edit signature**, so the clobber guard (`reports.py:304-311`) keeps it and no follow-up synthesis is dispatched (the edited capture is in the source set → marked `added`, `reports.py:125-131`); (2) the version store holds **pre-edit artifacts keyed by the post-edit content hash** — a future cache-hit restores wrong artifacts deterministically. *(Capture ADD mid-job is handled; only content EDITS fall through.)*

**Fix direction:** carry the job's input signature/capture-set (from payload time) through completion and stamp/record with *that*; if it differs from the current set, don't mark current — dispatch the follow-up. **Golden case:** start synthesis, edit a transcript mid-flight, complete → assert `report_synthesis.status != "current"` for the new signature and a follow-up job is dispatched; assert no `SessionReportVersion` whose hash covers content the artifacts don't reflect.

## S-F6 — Reconcile can hide a real allergy: mutual-duplicate cycles pass validation; stale decisions re-applied to the wrong patient
**T4 · HIGH (safety) · mechanism CONFIRMED-IN-CODE; model behavior speculative**

- `parse_safety_reconcile_output` blocks self-reference and unknown `ofKey` but **not cycles**: `{A: duplicate of B, B: duplicate of A}` validates (`contracts/safety_reconcile.py:54-60`). `apply_safety_reconciliation` annotates both (`patient_safety.py:159-184`); `patient_safety_flags_payload` then **skips every `reconcileStatus == "duplicate"`** (`patient_safety.py:145-147`) → the allergy disappears from the cross-visit card entirely, defeating the "never lose a distinct flag" floor (`docs/architecture/pipeline-versioning.md:142`).
- Cross-patient staleness: `safety_reconciliation` decisions are computed against the *then-assigned* patient's flags (context built at `worker_job_payload`, `session_processing.py:154-158`) but stored on the session and **re-applied later to whatever patient the session points at** — on cache-hit restore (`reports.py:397-403`) and on completion after a mid-job reassignment (`worker.py:1071-1079`).

**Fix direction:** in `apply_safety_reconciliation` (deterministic layer), break duplicate cycles (keep the oldest/first key) and drop decisions whose `ofKey` doesn't resolve to a *visible* flag on **this** patient; invalidate `safety_reconciliation` on reassignment. **Golden case:** decisions `{A:dup-of-B, B:dup-of-A}` over a patient holding both → assert exactly one remains visible; reassign then restore → assert no flag hidden by an `ofKey` absent from that patient.

## S-F7 — Rejections/confirmations silently unbind when the model rewords: text-keyed and language-keyed user state
**T4/T5 · MEDIUM-HIGH · CONFIRMED-IN-CODE**

- Safety-flag rejection is keyed `kind|normalized-text` (`patient_safety.py:39-41`). Any re-synthesis that rewords the flag mints a new key; the old rejection no longer matches → the **rejected wrong flag reappears and re-syncs onto the patient** (`worker.py:1071-1074`).
- Carried-forward confirmation is keyed raw `area|product` (`treatment_overlay.py:124-132` — no `norm_token`, no `areaCode`, report-language-dependent). Rewording or a report-language switch re-opens "confirm dose": the verify bar re-counts it (`CaptureScreen.tsx:224-226,244`) and `session_is_complete` flips the visit back to incomplete — a closed visit re-opens overnight after a re-synthesis.

**Fix direction:** key rejections by identity tolerant of rewording (carry rejections through the reconcile pass as candidates, or match by `sourceCaptureIds ∩ kind`); anchor `carried_forward_key` on `areaCode|norm(product)` like `treatmentKey`. **Golden case:** reject flag, re-synthesize a paraphrase → stays rejected; confirm carried dose, re-synthesize «گونه» → «گونه‌ها» → still confirmed.

## S-F8 — Overlay edits are invisible on the primary surfaces (and there is no UI to make them)
**T7 · MEDIUM · CONFIRMED-IN-CODE**

- The capture screen's treatment table reads **raw** `extractedMetadata.treatments` (`captureModel.ts:832-854`); `session_payload` (`capture_storage.py:131-…`) never folds the overlay.
- The report's `treatment-performed` prose is baked from raw treatments at finalize time (`session_processing.py:566-570`) and never re-rendered after an overlay edit — the printed/shared report shows the AI dose while smart lists / insights / memory show the human dose.
- `treatmentKey` appears **nowhere** in `apps/frontend/src` — the overlay endpoints (`sessions_api.py:136-158`) are unreachable from the UI; the `{aiValue, value}` disagreement surface promised in `pipeline-versioning.md:92-95` doesn't exist yet.

**Fix direction:** fold `effective_treatments` into `session_payload`'s treatments (or re-render the treatment-performed section on overlay write); the UI ships with the treatment-overlay epic (AES-1102+). **Golden case:** POST an overlay lot edit → GET session → payload treatments AND the rendered report line show the edited lot.

## S-F9 — Escalation marker lost if a correction lands while synthesis is in flight
**T6/T8 · MEDIUM · CONFIRMED-IN-CODE**

`synthesis_escalate_pending` lives in `extracted_metadata` (`synthesis_escalation.py:23`), but `complete_session_worker_job` **rebuilds** `extracted_metadata` from a preserved-key list that does not include it (`worker.py:1044-1067`; keys at 982-1034). A correction during a running job sets the marker; completion wipes it; the follow-up dispatch (`worker.py:1116-1118`) pops nothing → the escalated re-run happens on the cheap tier. Also: `pop` happens before `dispatch_session_processing_job` (`reports.py:459-471`) — a broker failure after commit consumes the hint without a run.

**Fix direction:** add `SYNTHESIS_ESCALATE_KEY` to the preserved set. **Golden case:** start job → overlay edit (marker set) → complete job → assert next dispatched job payload has `escalate: true`.

## S-F10 — Session status stomped to needs_review by late completions/restores
**T8/T5 · MEDIUM · CONFIRMED-IN-CODE**

`worker.py:1084` and `reports.py:404` unconditionally set `session.status = needs_review/unassigned` on synthesis completion / cache-hit restore. A clinician who hit "start review" (`sessions.py:602-610`, status `reviewing`) while a slow synthesis was in flight gets flipped back to `needs_review`. **Fix:** only settle status from `processing`/`draft` states. **Golden case:** status=reviewing + complete synthesis → status unchanged.

## S-F11 — Aftercare "conflicts"/"superseded" have no resolution path; `uncertaintyReasons` codes feed nothing
**T5 · MEDIUM · CONFIRMED-IN-CODE**

- Conflict/superseded cards render as ⚠ notes with **no dismiss/accept affordance** (`CaptureScreen.tsx:593-608` — remove button exists only on `includedAftercare` cards at 574-591). `dismissed_aftercare` *would* filter them (line 142) but nothing in the conflict card writes it — a permanent, unresolvable warning.
- The v2 `uncertainty_reasons` [{code,text}] field has **zero consumers**: no references outside its producer, not in `_ARTIFACT_METADATA_KEYS` (restores desync it from `uncertainties`), and the UI's review items come solely from the string-mapped `treatment_review` (every uncertainty → category `"ambiguous"`, no key → display-only note, `session_processing.py:460-462`, `LiveReport.tsx:141-146`). Resolver inventory: only `carried_forward` (keyed) has an actionable resolver + feeds the count; `ambiguous`/uncertainty items can never be cleared except by re-synthesis.
- Duplicate surfacing: the prompt asks for a `carried_forward_dose` uncertainty *and* the backend deterministically adds a carried-forward review item (`session_processing.py:434-444` + `460-462`) → the same dose produces one actionable row-chip **and** one un-clearable note.

**Fix direction:** wire `uncertaintyReasons.code` into `treatment_review` categories (drop the double-mapping, suppress `carried_forward_dose`-coded uncertainties when a keyed item exists); give conflict cards a dismiss that writes `dismissed_aftercare`. **Golden case:** synthesis emits a carried-forward treatment + its coded uncertainty → exactly one review item; conflict card → dismiss → stays gone across re-synthesis.

## S-F12 — Empty-but-valid synthesis replaces the baseline report with a hollow one; supersede across visits degrades to duplicates
**T2/T4 · MEDIUM-LOW · CONFIRMED-IN-CODE (apply); model behavior speculative**

- The only content gate is a non-empty summary; a response with all-empty sections yields 7 empty fixed sections which `report_model_from_session_processing_output` accepts (`session_processing.py:254-256, 685-700`) — the deterministic baseline (which had the transcripts/photos) is replaced by a near-empty report marked current. UI hides empty sections (`LiveReport.tsx:112`) so the body can render blank while Sources hold content.
- `supersedesCaptureId` validation only accepts this-session ids (`session_processing.py:417-431`); a prior-visit citation is cleared + BOTH rows kept + an "ambiguous" note — every cross-visit correction produces duplicate dose rows and an un-clearable note.
- Photos: nothing checks every photo capture appears in `media`; a model that omits image blocks silently drops photos the baseline used to show.

**Fix direction:** treat "no paragraph blocks at all across sections" as malformed (skip sentinel); accept prior-visit ids in the supersede resolver. **Golden case:** valid-JSON/empty-sections completion over a 4-capture session → baseline preserved.

## S-F13 — No meta-speech discipline in the synthesis prompt
**T3 · MEDIUM-LOW · SPECULATIVE (prompt gap confirmed)**

OOC handling is per-capture and upstream; a *mixed* capture (clinical dictation + instructions to staff/the app) reaches the synthesizer whole. `prompts/synthesis.py` has grounding and no-invention rules but **no directive to exclude administrative/meta/non-clinical speech from clinical sections**. **Fix:** explicit exclusion clause + eval fixture with interleaved meta speech asserting it never lands in sections/treatments.

## S-F14 — Assorted cross-surface drift
**T7 · LOW-MEDIUM · CONFIRMED-IN-CODE**

- Low-confidence thresholds disagree: backend review at `< 0.5` (`session_processing.py:28`) vs frontend styling at `< 0.6` (`captureModel.ts:866-868`) — a 0.55 row shows "low confidence" with no review item.
- Restore paths diverge: `reports.py:397-403` re-applies `safety_reconciliation` after restore; the capture-delete restore (`captures.py:287-293`) does not — and neither restores `uncertainty_reasons`/`safety_reconciliation`/`lang` (absent from `_ARTIFACT_METADATA_KEYS`, `report_versions.py:25-33`).
- `missing_lot` hints match rows by exact trimmed product text (`LiveReport.tsx:125-127, 325`) — a review item whose `product` fell back to `area` (`session_processing.py:410`) highlights no row.
- `update_session` accepts raw `treatments` (`sessions.py:259-260`) without `stamp_treatment_keys` — a staff bulk edit can strip keys and orphan the overlay.

## S-F15 — Lost-update window on `extracted_metadata`
**T8 · LOW · SPECULATIVE (structurally confirmed, timing-dependent)**

User-state endpoints (`confirm_carried_forward_dose`, `set_safety_flag_rejected`, overlay edits) and the completion handler (`worker.py:858-1111`) all read-modify-write the same JSON column in separate transactions with no locking. A rejection committed between the handler's read (`worker.py:947`) and its commit (`worker.py:1110`) is overwritten — the rejected flag returns and re-syncs to the patient. The capture screen actively encourages acting *during* the "Organizing with AI" window. **Fix:** `SELECT … FOR UPDATE` on the session row in the completion handler, or move user-state keys to dedicated columns/tables (the D2 "as written" design).

### Summary table

| # | Class | Defect | Severity | Status |
|---|-------|--------|----------|--------|
| S-F1 | T6 | Wrong-patient safety flags never dropped (AI reassign path; `str(session)` bug captures.py:283) | Critical | Confirmed |
| S-F2 | T6/T2 | Wrong-patient carry-forward survives reassignment; no re-synthesis dispatched | High | Confirmed |
| S-F3 | T1 | Malformed synthesis → permanent skip, no retry; `treatments: []` accepted silently | High | Confirmed |
| S-F4 | T4/T6 | Overlay edits destroyed by re-key/empty runs; priorKey can't rescue | High | Confirmed |
| S-F5 | T8 | Mid-job edit → stale report stamped current + poisoned version store | High | Confirmed |
| S-F6 | T4 | Reconcile duplicate-cycles can hide a real allergy; stale cross-patient decisions | High (safety) | Mechanism confirmed |
| S-F7 | T4/T5 | Text-keyed rejections/confirmations unbind on rewording/language switch | Med-High | Confirmed |
| S-F8 | T7 | Overlay invisible on capture screen/report prose; no UI exists yet | Medium | Confirmed |
| S-F9 | T6/T8 | Escalation marker wiped by in-flight completion | Medium | Confirmed |
| S-F10 | T8/T5 | Completion/restore stomps `reviewing` status | Medium | Confirmed |
| S-F11 | T5 | Aftercare conflicts unresolvable; `uncertaintyReasons` dead; carried-forward double-surfaced | Medium | Confirmed |
| S-F12 | T2/T4 | Hollow-but-valid synthesis replaces baseline; cross-visit supersede degrades | Med-Low | Confirmed (apply) |
| S-F13 | T3 | No meta-speech exclusion in synthesis prompt | Med-Low | Speculative |
| S-F14 | T7 | Threshold/restore/product-match drift | Low-Med | Confirmed |
| S-F15 | T8 | Read-modify-write races on extracted_metadata | Low | Structural |
