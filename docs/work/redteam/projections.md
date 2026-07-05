# Red-team report: cross-visit projection pipeline (memory · smart lists · insights · worklist)

> Verbatim agent report, 2026-07-05. Scope: `apps/backend/app/services/{patient_memory,patient_memory_intelligence,smart_lists,insights,worklist,treatment_overlay,patient_surface}.py`, `services/ai_jobs/{orchestration,worker,context}.py`, `apps/ai_engine/ai_engine/{jobs,prompts}/patient_memory.py`, `apps/frontend/src/features/memory/*`, contracts `docs/ai_engine/processing.md` §Patient memory, `docs/ux/screens/patients.md`.

## M-P1 — Patients-LIST read destroys real Pro AI memory with canned mock text AND suppresses the rebuild (T8 + T9 + T5)
**CONFIRMED-IN-CODE. Severity: CRITICAL** (silent, permanent quality regression on the flagship Pro artifact; destroys the incremental memory chain).

Ordinary scenario: Pro clinic. A capture upload flips memory to `updating`, `ready_at = +4s` (`capture_storage.py:393-394`, `patient_memory_intelligence.py:40,389-412`). Per the decoupled-trigger design, **no memory job is dispatched on completion** — only a read-trigger/line-up/sweep does. The capture chain + synthesis finish. The clinician returns to the **Patients home list** before opening the patient detail:

1. `list_patient_memory` calls `can_finalize_on_read` → True for Pro because **no memory job and no capture job is in flight** — exactly the post-visit resting state (`patient_memory_intelligence.py:194-205`, called at `patient_memory.py:423-426`).
2. `finalize_patient_memory_if_due` **replaces `patient.memory` wholesale** with the canned deterministic content of `generate_patient_memory` — "Memory spans 3 visits…", zero clinical facts — overwriting the accumulated real AI story/card/history (`patient_memory_intelligence.py:415-442`).
3. It stamps `updated_at = now`, later than every session's `updated_at`, so `patient_memory_is_stale` returns False (`patient_memory_intelligence.py:218-234`). The detail read-trigger (`patient_memory.py:678-686`), the line-up trigger, and the 30-min sweep (`orchestration.py:521,571`) are all gated on that staleness check → **the AI rebuild never fires** until the next content change.
4. Worse: the memory job is *incremental* (`priorMemory` + last 8 briefs, `patient_memory_intelligence.py:479-518`) — the next rebuild's prior is the canned text; the longitudinal story older than 8 visits is unrecoverable.

The list read wins this race whenever it happens first — the common navigation order. The "safety net" comment (`patient_memory.py:420-422`) describes a job that *failed*; but "never dispatched" is the **normal** post-capture state in the decoupled model. A leftover of the pre-AI mock design colliding with the real job.

**Fix direction:** (a) the Pro list read must never write canned content — call `maybe_refresh_stale_patient_memory` from the list too, or make the safety net only flip `status→ready` while **keeping prior summary/history/card and NOT stamping `updated_at`**; (b) stamp memory `updated_at` from the *inputs snapshot time*, not finalize time.
**Golden case:** Pro patient with a real AI memory (`source: ai:*`); upload a capture; let all jobs settle; `GET /patients/memory` (list); assert `patient.memory.summary` still contains the prior clinical facts and `patient_memory_is_stale` is still True; then `GET /patients/{id}/memory` and assert a `patient_memory` job was dispatched.

## M-P2 — Reassignment A→B never invalidates patient A's memory: A's brief keeps quoting B's visit forever (T9 + T7 + T2)
**CONFIRMED-IN-CODE. Severity: HIGH.**

`assign_session_patient` handles the former patient for **safety flags only** (`sessions.py:573-576`) and escalates the *session's* next synthesis — but never touches A's `patient.memory` and never marks/dispatches a refresh for A. The B side self-heals; A's staleness is computed **only over A's remaining sessions** (`patient_memory_is_stale`) — removing a session changes nothing A-side. Same gap on the capture-delete de-effect path (`captures.py:274-283` + `patient_assignment_timeline.py:169-207`). `mark_patient_memory_updating` has exactly one call site — capture **upload** (`capture_storage.py:394`); the module docstring's claim that "an assignment" triggers it (`patient_memory_intelligence.py:5`) is false.

Staleness triggers cover *additions*, not *removals/reassignments*.

**Fix direction:** in `assign_session_patient` and `apply_active_patient_assignment`, when `previous != next`, `mark_patient_memory_updating(db, previous)` **and** record a patient-level "content removed at T" watermark that `patient_memory_is_stale` also consults; or store the set/hash of session ids the memory was built from.
**Golden case:** build A's AI memory from 2 visits; reassign visit 2 to B; open A → A's memory refreshes and no longer mentions visit-2 treatments; A's line-up card `storySoFar` rebuilt.

## M-P3 — Public share pages are never invalidated by reassignment/de-effecting (T6)
**CONFIRMED-IN-CODE. Severity: HIGH (privacy).** A share freezes `patientName` + sections + treatments + media into an immutable snapshot under a live token (`patient_surface.py:217-256`). If the source session is later reassigned A→B, or its captures deleted/undone, **nothing revokes or flags the share** — no `PatientShare` reference exists anywhere outside `patient_surface.py`. B's visit content remains publicly served under A's name at `/share/{token}`.

**Fix direction:** on reassignment/unassignment and on capture delete, revoke (or mark "stale — review") active shares whose `session_id` matches; surface in the needs-input inbox.
**Golden case:** create a share for A's session; reassign to B; `GET /share/{token}` → revoked/410, not B's photos under A's name.

## M-P4 — Line-up card "since last visit" and the share page's treatment lines bypass the treatment overlay (T7)
**CONFIRMED-IN-CODE. Severity: MEDIUM-HIGH** (the AES-1101 safety class: a clinician-corrected dose/lot/product not reaching a surface).

`treatment_overlay.py:17-18` declares `effective_treatments` "the ONLY treatments read". Two violators:

- `patient_memory.py:577-586` — `_session_treatment_phrases` reads **raw** `metadata.get("treatments")` for the line-up card's `sinceLastVisit` line (`patient_memory.py:589-620,654`). A corrected dose shows the **old AI value** on the worklist recap. Doc/code conflict (`processing.md` claims "grounded in the latest visit's treatments[]").
- `patient_surface.py:166-190` — `_curated_treatment_lines` reads raw treatments for a newly created share's "what we did" lines; `area`, `product`, `brand` are all overlay-editable.

Confirmed clean: smart lists/ledger/recall (`smart_lists.py:93-96`), insights (`insights.py:258-261`), memory job brief (`patient_memory_intelligence.py:453-461`).

**Fix direction:** one-line changes — `effective_treatments(session)` in both readers.
**Golden case:** visit with "Voluma 0.3 mL"; overlay-edit to "0.5 mL"; line-up `sinceLastVisit` and a fresh share both render 0.5.

## M-P5 — Memory job races a mid-flight content change: snapshot at start, freshness stamped at completion (T8 + T9)
**CONFIRMED-IN-CODE (window real; hitting it needs timing). Severity: MEDIUM-HIGH.**

The worker builds the payload at `start_job` (`worker.py:262-268` → `patient_memory_job_payload`, `orchestration.py:582-604`) but completion stamps `updated_at = completed_at` (`orchestration.py:607-614` → `apply_patient_memory_output`, `patient_memory_intelligence.py:598-625`). Any session change landing between payload build and completion is (a) absent from the memory, (b) has `session.updated_at < memory.updated_at` → never repaired. The per-patient dedup (`orchestration.py:474-476`) blocks a follow-up while the job runs. Dedup is also TOCTOU-racy across processes (no DB uniqueness on active memory jobs) — SPECULATIVE, small window.

**Fix direction:** snapshot `built_from = max(session.updated_at)` (or `utc_now()`) at payload-build and write *that* as `memory.updated_at` on completion.
**Golden case:** start a memory job; before completion, edit a treatment overlay on one visit; complete → `patient_memory_is_stale` is True.

## M-P6 — Fair-use-parked capture jobs freeze memory in "updating"; the UI stops polling after 36 s (T5)
**CONFIRMED-IN-CODE. Severity: MEDIUM.** Parked jobs stay `queued` (`orchestration.py:300-317`); `patient_has_pending_capture_jobs` counts `queued` (`patient_memory_intelligence.py:174-191`) → finalize blocked, dispatch blocked, memory `updating` for as long as the budget is exhausted. The frontend poll gives up after 12×3 s (`PatientsHome.tsx:368-389`) with no tie-in to the usage-limit state (`MemoryCards.tsx:362-385`). Same static-pill whenever a rebuild takes > 36 s.

**Fix direction:** when the block reason is a parked job, surface the existing usage-limit state instead of `updating`; frontend resumes polling with backoff.
**Golden case:** park a capture job via the budget gate; open the patient; the memory status is not an eternal `updating` (or carries a `reason` the UI maps).

## M-P7 — Archived/cleaned-up patients live on in the worklist (and can be newly lined up) (T5 + T7)
**CONFIRMED-IN-CODE. Severity: MEDIUM.** `create_worklist_entry` validates existence but not `PatientStatus.active` (`worklist.py:78-82`); `list_worklist` has no status filter (`worklist.py:170-180`) — an archived patient still sits in "Today / up next" while memory list (`patient_memory.py:325`), smart lists (`smart_lists.py:161`), and the panel (`insights.py:526-528`) exclude it. `get_patient` has no status filter (`patients.py:60-70`) so a visit can run against an archived identity. `create_worklist_entry` even dispatches a memory job for it (`worklist.py:132-139`).

**Fix direction:** filter/auto-cancel `waiting` entries for non-active patients; block line-up creation; cancel waiting entries inside the archive path.

## M-P8 — Insights counts visits of archived patients; panel and smart lists don't (T7)
**CONFIRMED-IN-CODE. Severity: LOW-MEDIUM.** `_load_visits`/`_last_visit_per_patient` never join `Patient` (`insights.py:235-262,294-304`); `totalActive`, new-patients, recency cohorts (`insights.py:283-291,522-533`) count active only — two tabs of the same screen disagree after any cleanup. **Fix:** decide once, encode in one loader.

## M-P9 — Rename semantics: memory prose is the one projection that can cache the old name, and rename never marks memory stale (T9 + T4 + T2)
**Severity: MEDIUM. Mixed.** Live-read surfaces are clean (worklist `worklist.py:55`, rosters `smart_lists.py:198,373`, memory rows `patient_memory.py:267`, Q&A headers `qa.py:476,733,841` all read `display_name` at request time). Gaps: (a) CONFIRMED — `patient_memory_is_stale` only looks at *session* timestamps; a rename never triggers a rebuild, so a name baked into memory prose stays until the next visit change. (b) SPECULATIVE — the payload hands `displayName` to the model (`patient_memory_intelligence.py:507`) relying on a prompt instruction not to use it (`prompts/patient_memory.py:36-38`). Frozen share snapshots keep the old name by design — state it in the rename spec.

**Fix direction:** stop sending `displayName` to the memory model; include `patient.updated_at` in the staleness max.
**Golden case (eval):** memory output contains neither the payload `displayName` nor any token of it, fa + en.

## M-P10 — Memory-level summary leak: no meta-speech/assignment-chatter guard anywhere in the chain (T3)
**SPECULATIVE (prompt-level). Severity: MEDIUM.** The memory brief grounds in each session's `generated_summary` verbatim (`_session_brief`, `patient_memory_intelligence.py:464-476`). Neither the synthesis prompt nor the memory prompt has an "ignore administrative/assignment chatter" clause — the incident class has a second life at the memory level, where a one-visit leak **compounds across visits** via the incremental `priorMemory` chain.

**Fix direction:** exclusion clause in both prompts; memory-eval fixture with planted meta-speech asserting it doesn't survive into `summary/storySoFar`.

## M-P11 — Wrong+right identity after cleanup: no double-count in rosters, but memory "merge" is prompt-trust (T2)
**Severity: LOW-MEDIUM.** Recall/smart lists key strictly on live `patient_id` (`smart_lists.py:169-190,398-427`) — no double-counting, provided the wrong identity is archived. The right patient's rebuilt memory receives `priorMemory` + last-8 briefs which now overlap moved visits; dedup is delegated entirely to the model. **Golden case:** move visits 3-4 in from a wrong identity → rebuilt story mentions each treatment once.

## M-P12 — Tier-boundary leaks (Basic⇄Pro) (T7, edge)
**CONFIRMED mechanisms. Severity: LOW.** Downgrade: `_row_payload` serves persisted Pro AI summary (`patient_memory.py:252-270`) and stored Pro `history` (`patient_memory.py:747`) to a Basic tenant until re-finalize. Upgrade: stored deterministic memory has fresh `updated_at` → not stale → keeps mock memory until the next change. `tenant_tier` defaults **unknown tier strings to "pro"** (`patient_memory_intelligence.py:128-131`) — fail-open.

**Fix direction:** gate persisted summary/history on tier matching `memory.mode`; default unknown tier to "basic".

## M-P13 — Minor/latent (grouped)
- T1: `complete_patient_memory_worker_job` marks `succeeded` when the patient row is gone (`orchestration.py:610-615`) — no log distinguishing applied vs dropped.
- T4: model returns no `card` → worker substitutes the *deterministic* card next to the *AI* summary (`jobs/patient_memory.py:88`) — worklist recap can contradict the memory card.
- T7: passive list viewer (reception tablet) has no poll — rows can show `updating` indefinitely (`PatientsHome.tsx:359-363`).
- T2: needs-input pre-filter statuses (`NEEDS_INPUT_CARRIER_STATUSES`, `patient_memory.py:52-56`) exclude `reviewing`/`draft` sessions carrying `treatment_review` (likely low impact).

## Ranked summary

| # | Defect | Tax. | Status | Severity |
|---|--------|------|--------|----------|
| M-P1 | List-read finalize overwrites Pro AI memory with canned text + suppresses rebuild | T8/T9/T5 | CONFIRMED | **Critical** |
| M-P2 | Reassignment never invalidates former patient's memory | T9/T7 | CONFIRMED | **High** |
| M-P3 | Public shares survive reassignment/de-effect | T6 | CONFIRMED | **High** |
| M-P4 | Line-up `sinceLastVisit` + share treatment lines bypass `effective_treatments` | T7 | CONFIRMED | Med-High |
| M-P5 | Memory freshness stamped at completion, snapshot at start | T8/T9 | CONFIRMED | Med-High |
| M-P6 | Budget-parked jobs freeze memory `updating`; UI poll caps at 36 s | T5 | CONFIRMED | Medium |
| M-P7 | Archived patients persist in / can be added to the worklist | T5/T7 | CONFIRMED | Medium |
| M-P8 | Insights counts archived patients' visits; siblings don't | T7 | CONFIRMED | Low-Med |
| M-P9 | Rename never marks memory stale; name reaches the model on trust | T9/T4/T2 | Mixed | Medium |
| M-P10 | No meta-speech guard in synthesis-summary → memory chain (compounds via priorMemory) | T3 | SPECULATIVE | Medium |
| M-P11 | Post-cleanup memory merge dedup is untested prompt-trust | T2 | SPECULATIVE | Low-Med |
| M-P12 | Tier downgrade/upgrade leaks; unknown tier defaults to Pro | T7/T2 | CONFIRMED | Low |
| M-P13 | Silent job success on missing patient; card fallback mismatch; passive-list spinner; needs-input pre-filter | mixed | Mixed | Low |

Highest-leverage single fix: M-P1+M-P5 together — make `memory.updated_at` mean "inputs as of T" (stamped from the payload snapshot) and make the Pro read path never write content; M-P2 then needs only the former-patient `mark_patient_memory_updating` + a removal-aware staleness signal.
