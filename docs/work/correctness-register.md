# Correctness register — deduped findings + track assignments

**Status:** tracks E1/E2/E3/D+ **MERGED to main 2026-07-06** (`8b104d2`, PR #3 — CI green).
Remaining: the Track A/B/C addenda below (ride the Batch-2 UX epics) + the E1 fast-follow
(one-tap rename/unassign endpoint — see launch-backlog.md, assigned to Track B). Index over the
four verbatim reports in [redteam/](redteam/README.md) (~44 findings, ~36 CONFIRMED-IN-CODE).
Delete this doc + redteam/ when the addenda fold with Batch 2.

## The five structural invariants (design rules, not per-bug patches)

Every track enforces these where its files are concerned; tests assert them:

1. **INV-LOCK — serialize `session.extracted_metadata` writes.** All writers (job completions,
   user-state endpoints, staff assignment) take `SELECT … FOR UPDATE` on the session row (or merge
   append-only keys by event id). Kills: A-F1, A-F2, S-F5, S-F9, S-F15, M-P5-adjacent.
2. **INV-SILENT — no silent exits.** A confident identity detection or an explicit user instruction
   must end in exactly one of: applied effect · visible suggestion · visible "couldn't act" notice.
   Completion-time assertion + full-lattice unit tests. Kills: A-F7, A-F9, A-F12, Q-1, S-F3(a),
   plus the original incident cluster.
3. **INV-SNAPSHOT — stamp freshness from job-START inputs.** Signatures, `updated_at`, version
   hashes are computed from the payload-build snapshot, never from completion-time DB state.
   Kills: S-F5, M-P1(b), M-P5.
4. **INV-INVALIDATE — state-changing events have invalidation edges.** Reassignment, rename,
   capture-delete/de-effect, transcript edit, OOC marking, exemplar exclusion each enumerate and
   invalidate/refresh their dependents (synthesis, memory of BOTH patients, safety flags,
   reconcile decisions, shares, QA drafts, worklist). Kills: A-F3, A-F4, A-F6, S-F1, S-F2, S-F6,
   M-P2, M-P3, M-P7, M-P9, Q-4, Q-5.
5. **INV-IDENTITY-KEYS — user decisions bind to stable identity, not text.** Rejections,
   confirmations, overlay entries key on `areaCode|norm(product)` / reconcile-carried identity /
   priorKey-first rebind; un-bindable user state is parked + surfaced, never deleted.
   Kills: S-F4, S-F7.

## Track assignments

### Track E1 — identity & assignment semantics
Owner files: `services/ai_jobs/{intents,orchestration,recovery}.py`, the assignment block of
`worker.py` (`complete_worker_job`), `patient_assignment_timeline.py`, `patient_matching.py`,
`patients.py`, `prompts/transcription.py` (+ its eval), minimal chip variants inside existing
resolver components + i18n.

- The original incident cluster — full owner-approved spec in [redteam/incident-cluster.md](redteam/incident-cluster.md): rename semantic,
  echo-suppression correction detection, never-silent, «درستش»/«اصلاح بشه» explicit
  classification, meta-only capture exclusion flag (apply side in E2), orphan archive, dead-zone
  create+assign fallback.
- [A-F1](redteam/assignment.md) chain double-dispatch + per-session serialization (INV-LOCK).
- [A-F4] OOC veto on assignment + staff mark-OOC de-effect path.
- [A-F5] national-ID vs spoken-name cross-check → demote to possible_match on mismatch.
- [A-F6] transcript-edit re-runs matching → suggestion chip (INV-INVALIDATE).
- [A-F7] late-recovery inert assignment → conflict chip (INV-SILENT).
- [A-F8] note identity/intent extraction (deterministic ID/phone regex minimum; LLM Pro);
  suggestion-only. Photos: defer, note in register.
- [A-F9] detach/negation intent → suggested unassign (schema + prompt + apply).
- [A-F11] `suggested-reassignment` needs-input kind (owner-scoped when policyDeferred);
  persistent dismiss recorded as feedback.
- [A-F12] explicit-no-effect → actionable "couldn't apply — assign manually" (INV-SILENT).
- [A-F13] stale candidate cleanup + needs-input key mismatch fix.
- [A-F14/A-F15] transcription prompt: two-names/self-correction rules + "admin/assignment
  instructions ARE visit content" OOC carve-out. Eval-gated.
- [A-F16] AI patient creation runs the duplicate guard; strong hit → suggest not create.
- [A-F10] session-status stomp in recovery/skip paths (shared with E2 — E1 owns recovery.py side).

### Track E2 — synthesis apply, user-state & safety
Owner files: `complete_session_worker_job` + skip/fail paths in `worker.py`, `reports.py`,
`report_versions.py`, `treatment_overlay.py`, `patient_safety.py`, `session_processing.py`,
`sessions.py` user-state endpoints, `prompts/synthesis.py` + `contracts/synthesis.py` (+ evals).

- [S-F1](redteam/synthesis.md) **CRITICAL**: safety-flag drop+sync inside
  `apply_active_patient_assignment`; fix the `str(session)` bug at `captures.py:283`.
- [S-F2] reassignment force-dispatches re-synthesis; invalidate carried-forward rows +
  confirmations (with A-F3; INV-INVALIDATE).
- [S-F3] malformed synthesis → bounded retry; treatments 3→0 on unchanged captures → review item.
- [S-F4] overlay rebind: priorKey-first rule + `treatment_overlay_orphans` parking + review chip
  (INV-IDENTITY-KEYS).
- [S-F5] completion stamps job-start signature/capture-set; mismatch → not current + follow-up
  (INV-SNAPSHOT).
- [S-F6] reconcile cycle-breaking + ofKey-must-resolve-visible-on-THIS-patient; invalidate
  reconcile on reassignment.
- [S-F7] rejection keys tolerant of rewording; carried keys on `areaCode|norm(product)`.
- [S-F9] preserve `SYNTHESIS_ESCALATE_KEY` across completions; pop-after-dispatch.
- [S-F10] status settles only from processing/draft.
- [S-F11] backend: wire `uncertainty_reasons` codes into `treatment_review` categories;
  de-duplicate carried-forward double-surfacing. (Conflict-card dismiss UI → Track B.)
- [S-F12] hollow-report floor (no paragraph blocks anywhere = malformed); accept prior-visit
  supersede ids; photo-coverage check vs baseline.
- [S-F13 + M-P10 + incident Fix 4] meta-speech exclusion clauses in synthesis + summary +
  patient-memory prompts, eval-gated with planted-meta fixtures.
- [S-F14] threshold unification, `_ARTIFACT_METADATA_KEYS` completeness (uncertainty_reasons,
  safety_reconciliation, lang), capture-delete restore parity, `update_session` stamps keys.
- [S-F15] INV-LOCK on completion handler + user-state endpoints.
- [S-F8] backend half: `session_payload` folds `effective_treatments`; re-render
  treatment-performed on overlay write. (UI half ships with Track B's overlay epic.)

### Track E3 — projections, shares & lifecycle
Owner files: `patient_memory.py`, `patient_memory_intelligence.py`, `patient_surface.py`,
`worklist.py`, `insights.py`, `smart_lists.py` (read paths), `prompts/patient_memory.py` (+ eval).

- [M-P1](redteam/projections.md) **CRITICAL**: Pro list-read must never write canned memory;
  finalize keeps content + doesn't stamp; list path may dispatch refresh (INV-SNAPSHOT).
- [M-P2] reassignment/de-effect marks the FORMER patient's memory updating + removal-aware
  staleness (built-from session-set hash or removal watermark).
- [M-P3 + Q-4] share invalidation: reassignment auto-revokes; corrections/safety-flag additions
  mark `stale_since` + needs-attention row; `public_share_media` checks patient ownership.
- [M-P4] `effective_treatments` in `_session_treatment_phrases` + `_curated_treatment_lines`.
- [M-P5] memory `updated_at` = payload-snapshot time (INV-SNAPSHOT).
- [M-P6] parked-budget memory status carries a reason (UI mapping → Track A).
- [M-P7] worklist filters/auto-cancels non-active patients; archive path cancels entries.
- [M-P8] insights ↔ panel archived-patient consistency (one loader decision).
- [M-P9] stop sending `displayName` to the memory model; `patient.updated_at` in staleness;
  rename-name eval case.
- [M-P11] moved-visits memory-dedup eval fixture.
- [M-P12] tier fail-closed (`unknown → basic`); persisted summary/history gated on
  tier-matches-mode.
- [M-P13] minors as time permits (log applied-vs-dropped, card fallback mismatch note).
- [Q-6] lot-pattern filter at `_curated_media` snapshot time.
- [Q-9 archive half] revoke threads/shares on patient archive (token rotation → Track D+).

### Track D+ — QA hardening (extends the QA harvest-signals prompt)
Owner files: `services/qa.py`, `qa_knowledge/`, `qa_api.py`, `features/qa/*`,
`prompts/qa_draft.py` + `qa_revise.py` (+ evals), `ai_usage` metering sets, harvest script.

- [Q-1](redteam/qa.md) **HIGH**: visible failure for the revise fallback; never render "Revised"
  for non-`ai-voice:` sources (INV-SILENT).
- [Q-2] `DRAFT_REVISING` in the self-heal guard + `draft_job_id` optimistic lock.
- [Q-3] unconditional never-copy rule incl. priorAnswers; server-side greeting-name stripping;
  eval gate: exemplar/prior-answer-only numbers forbidden + name-leak case.
- [Q-5] draft invalidation on reassign/re-route/exclusion; document memory-append permanence.
- [Q-7] qa jobs in `fail_worker_job` → `DRAFT_FAILED`; frontend polls pending drafts.
- [Q-8] ask rate-limit + pending cap; qa job types join usage metering.
- [Q-9] token rotation on thread re-activation.
- [Q-10] `language` on the public QA payload + localize `PatientQaPage`; visibly mark the
  deterministic fallback. (Public-page i18n was deferred once — this closes it for QA.)
- [Q-11] CLAUDE.md §4 "qa evals known debt" note is stale → fix; badge refresh on ask.
- Plus the original Track-D scope: failure auto-detection harvest signals (revise/replace/manual
  edit/dismiss → ai_feedback_events).

### Track A/B/C addenda (UX tracks, unchanged scope plus)
- **A:** memory-list poll with backoff + parked-budget usage-limit state mapping (M-P6 UI,
  M-P13 passive-list note).
- **B — LANDED** (Batch-2 session-surface, 2026-07-06): phantom verify-count fix + reachable-resolver
  invariant; aftercare conflict-card dismiss writing `dismissed_aftercare` (S-F11 UI); coded review
  items render actionably (no silent drop / double-surface); overlay UI reads folded/effective
  treatments + renders the `{aiValue, value}` reconcile (S-F8 UI) + the E1 one-tap identity chips. Folded
  into [capture.md](../ux/screens/capture.md) + [session-review.md](../ux/screens/session-review.md).
- **C:** unchanged.

## Eval additions (golden-case classes, owner-approved 2026-07-05)
Each track authors the golden cases sketched in its report entries. Classes: assignment decision
lattice (incl. OOC-veto, national-ID mismatch, two-names, self-correction, detach, note-identity);
reassignment invalidation (re-synthesis, memory both-sides, shares, safety flags, reconcile);
overlay/user-state persistence across re-synthesis (priorKey rebind, reworded flags, language
switch); meta-speech exclusion (synthesis sections, summaries, memory chain); zero/hollow-output
guards; QA cross-patient leak gates; memory rename/moved-visits. Fixture rule stands: non-text
fixtures only from the owner, never generated; the owner's own prod/dev clips are approved for
reuse.
