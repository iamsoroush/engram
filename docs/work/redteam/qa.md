# Red-team report: patient-facing AI paths (qa_draft · qa_revise · public surfaces · caption)

> Verbatim agent report, 2026-07-05. Scope: `apps/ai_engine/ai_engine/jobs/qa_draft.py`, `qa_revise.py`, `prompts/qa_draft.py`, `prompts/qa_revise.py`, `apps/backend/app/services/qa.py`, `qa_knowledge/{retrieval,library}.py`, `patient_surface.py`, `qa_api.py`, `ai_jobs/worker.py`, `ai_usage/service.py`, frontend `features/qa/*` + `features/patient-surface/*` + `SharePatientSheet.tsx`, `jobs/capture_photo.py` + `prompts/caption.py`, evals `qa_draft_eval.py`/`qa_revise_eval.py`. Ranked by patient-harm severity.

## Q-1 — HIGH — Voice edit silently no-ops AND falsely claims success (T1)

Doctor records "add: she must NOT massage the area" as a voice edit. The model returns unusable output (or audio fetch fails, or gateway unconfigured). The pipeline falls back to *the unchanged draft* — and the UI displays "✨ Revised" over the identical text. Doctor trusts it, taps Send; the safety correction never reaches the patient.

Confirmed chain: `jobs/qa_revise.py:40-49` fallback = `mode:"revise", reply: fallback.reply`; `qa.py:1170` `deterministicFallback = {"mode":"revise","reply": current_draft}`; `qa.py:1189-1192` completion writes `DRAFT_READY`, `draft_source="mock-deterministic"`; `qa.py:1119` `draftMode` derived only from `ai-voice:` sources → null for the fallback; `useVoiceEdit.ts:58` coerces null mode to `"revise"`; `DoctorQaInbox.tsx:443-449` renders the "voiceRevised" ✨ banner. `draftSource` is never rendered anywhere.

**Fix:** fail the revise visibly (`draftStatus:"failed_revise"`, "Couldn't apply your voice note — draft unchanged") or propagate `source` and treat non-`ai-voice:` as failure. **Golden case:** gateway forced-unusable → doctor-visible error state, NO "revised" banner; e2e: textarea unchanged AND error present.

## Q-2 — HIGH — Inbox self-heal races the in-flight voice edit and can clobber it (T8 + T5)

`qa.py:779` — `if question.status != Q_PENDING or question.draft_status in {DRAFT_PENDING, DRAFT_READY}: return False` — `DRAFT_REVISING` falls through to `_create_and_dispatch_draft_job`, which resets `draft_status = DRAFT_PENDING` and overwrites `draft_job_id` (`qa.py:791-807`). Any inbox read during a voice edit dispatches a fresh qa_draft job; two jobs race, last writer wins (`qa.py:994`, `qa.py:1189`); the doctor's spoken edit can be overwritten by a regenerated generic draft. The 1.5s poll sees `pending` (≠ `revising`) mid-race and reports failure for an edit that later lands (`useVoiceEdit.ts:57`).

**Fix:** add `DRAFT_REVISING` to the guard set; completions check `question.draft_job_id == job.id` (optimistic lock). **Golden cases:** revising + `qa_inbox` → no new AiJob; stale qa_draft completing after a newer qa_revise → revise text survives.

## Q-3 — HIGH — Cross-patient clinical facts flow into drafts via `priorAnswers`; the eval gate is structurally blind to copied exemplar/prior-answer doses (T4)

- `qa.py:848-864` `_prior_doctor_answers` filters by **tenant + doctor only**, never by patient — the doctor's replies to all other patients (greetings with names, doses) are injected as grounding.
- `prompts/qa_draft.py:33-45` — the "NEVER copy a specific dose/product/brand" rule renders **only inside the exemplars section and only when `retrievedExemplars` is non-empty**. Zero exemplars (new clinic, retrieval failure — swallowed at `qa.py:936-940`) → no cross-patient guard at all. `prompts/qa_revise.py` never has the rule.
- Eval blindness: `qa_draft_eval.py:85-96` `_input_numbers` **whitelists every number in priorAnswers and retrievedExemplars**, so the no-invented-numbers gate cannot flag a dose copied from another patient's reply. No case tests a patient NAME embedded in an exemplar/prior answer.

**Fix:** (a) unconditional never-copy rule covering priorAnswers; (b) strip/replace greeting names server-side in prior answers; (c) eval gate class: numbers appearing *only* in exemplars/priorAnswers are forbidden unless generic + a name-leak case. 

## Q-4 — HIGH — No "outstanding share predates a correction" surface anywhere, including safety corrections (T7/T9)

The snapshot is immutable by design (`patient_surface.py:193-256`) — but **nothing** cross-references corrections with active shares: `assign_session_patient` (sessions.py:488-600) touches neither `PatientShare` nor `QaThread`; no "created before latest report change" flag exists in `staff_share_payload` (`patient_surface.py:259-280`). Sharper sub-case: `public_share_media` (`patient_surface.py:374-402`) re-checks **tenant only**, not patient ownership — a photo shared under patient A's token, later reassigned to B, keeps streaming to A indefinitely.

**Fix:** on safety-flag add / report correction / reassignment, mark affected active shares `stale_since` + surface a needs-attention row; auto-revoke on reassignment; media check patient ownership at read. **Golden cases:** share → reassign → flagged/revoked + media 404; share → add safety flag → staff share list shows stale warning.

## Q-5 — MED-HIGH — Wrong-patient / stale grounding of drafts is never invalidated (T9)

Grounding is read at draft-time (`qa_draft_worker_payload`, `qa.py:912-969`) — correct — but nothing invalidates a `ready` draft when: (a) the grounding visit is reassigned away (no reassignment hook touches `QaMessage.draft*`); (b) the thread is re-routed — the new doctor inherits a draft signed with the previous doctor's name (`doctorName` baked at `qa.py:928`; `route_thread` at `qa.py:405-426` never re-drafts); (c) an exemplar is excluded (`library.py:246-264` affects future retrieval only) — the Library "exclude" UI implies retroactive removal it does not deliver; (d) the sent exchange appended to `patient.notes` (`qa.py:644-656`) grounds future drafts forever even after the clinic decides the reply was wrong.

**Fix:** on reassignment/re-route/exclusion, reset affected pending questions' `draft_status` to `none` (self-heal re-drafts); document memory-append permanence. **Golden case:** ready draft → reassign grounding visit → inbox read → fresh draft job dispatched.

## Q-6 — MED-HIGH — Lot/batch numbers reach the patient through prefilled AI captions, violating the withholding contract (T7)

The caption prompt *mandates* reading brand + lot (`prompts/caption.py:34-36`; high-detail re-read `capture_photo.py:108-113`). The share sheet prefills photo captions with the AI caption (`SharePatientSheet.tsx:157`) and the backend snapshots it verbatim (`patient_surface.py:126`). The contract says lot/batch **always withheld** (`patient-surface.md:43`) and `_curated_treatment_lines` enforces it for treatment lines (`patient_surface.py:166-190`) — the caption channel bypasses it entirely.

**Fix:** filter lot-pattern tokens at `_curated_media` snapshot time (server-side, per the contract). **Golden case:** caption "Botox vial, lot A1234B" → share with default caption → public payload contains no lot token.

## Q-7 — MEDIUM — Terminally failed qa_draft = stuck "Drafting…" forever; frontend never polls initial drafts (T5)

`fail_worker_job` (`ai_jobs/worker.py:1159-1220`) handles capture and session jobs only — a non-retryable qa job failure never sets `DRAFT_FAILED`; the self-heal **skips** `DRAFT_PENDING` (`qa.py:779`) → stuck "Drafting…" (`DoctorQaInbox.tsx:322,425`) indefinitely. The inbox does no polling for pending initial drafts. The contract's self-heal claim (`aes-pro-qa-api.md:20-21`) is false for this state.

**Fix:** `fail_worker_job` sets `DRAFT_FAILED` for qa jobs; frontend polls `draftStatus === "pending"`. **Golden case:** non-retryable qa_draft failure → next inbox read dispatches a replacement.

## Q-8 — MEDIUM — Public `/qa/{token}/ask` is unthrottled and each ask buys an uncapped LLM call (T6/abuse)

`qa_api.py:307-310` — no rate limit, no per-thread pending cap; every ask dispatches a draft job (`qa.py:758-759`); qa jobs are in neither metering set (`ai_usage/service.py:23-29`) so the fair-use cap never pauses them. A leaked token = unbounded spend + inbox flooding.

**Fix:** per-token rate limit + concurrent-pending cap (e.g. 3); include qa jobs in usage metering. **Golden case:** 10 rapid asks → ≤N accepted, ≤N jobs.

## Q-9 — MEDIUM — Token lifecycle gaps: revoked Q&A token re-armed verbatim; archived patients keep live tokens (T6)

`create_or_get_thread` (`qa.py:344-350`) re-activates a revoked thread with the **same token** — a leaked URL is silently re-armed by the next "Share Q&A" tap. Neither `qa.py` nor `patient_surface.py` checks `PatientStatus` — an archived patient keeps a live public thread and shares.

**Fix:** rotate the token on re-activation; revoke threads/shares on patient archive. **Golden case:** revoke → re-open → `token != old_token`, old link 404s.

## Q-10 — MEDIUM — Language inconsistency on the patient surfaces + English fallback drafts on fa clinics (T7/T2)

- The QA public payload has no language field (`qa.py:707-714`); `PatientQaPage.tsx` is hardcoded English while `PatientSharePage.tsx:81-83` localizes — the same clinic's two public pages contradict.
- `_qa_draft_fallback` (`qa.py:867-909`) is a hardcoded English scaffold; with a Persian exemplar it splices Persian guidance into English framing — and per Q-1 it is visually indistinguishable from a real AI draft.

**Fix:** add `language` to the public QA payload + localize the page; mark the deterministic fallback visibly ("Starter reply — please review").

## Q-11 — Checked and OK / minor

- Caption OOC misfire is NOT silent (visible chip + "Mark relevant" override: `session_processing.py:34-46`, `LiveDraftReport.tsx:195-259`). Residual: OOC photos excluded from memory photo selection (`patient_memory.py:525`) with no chip there.
- Mine/Clinic badge-vs-list incident is fixed (`qa.py:524` includes unrouted in mine; badge uses mine, `App.tsx:188`). Residual: badge refreshes only on mount/inbox load (`App.tsx:183-195`).
- Send-vs-revise races are guarded server-side (`qa.py:571,994,1189`).
- Evals exist and are registered (`run_all.py:38-39`) — CLAUDE.md §4's "known debt" note is stale; update it.
- Withholding projections structurally sound on both public payloads (`qa.py:669-714`; `patient_surface.py:331-358`).
- Orphaned transient voice objects on never-completing jobs (`qa.py:1201-1208`) — acknowledged best-effort.

**Top three if only three get fixed:** Q-1, Q-2, Q-3 — all sit directly on the send-to-patient path and are cheap, contained fixes.
