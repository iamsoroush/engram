# Technical decisions — dated decision log

One file per decision, named `YYYY-MM-DD-slug.md` (the date the decision landed). These are
system-state: decisions future agents and developers must respect. **Scan the index below (it is on
the every-task reading list); open only the decisions your task touches.**

- **Add** a decision: create a new dated file **and its one-line index entry below** (CI fails on a
  decision file missing from this index). Never append an unrelated decision to an existing file —
  per-decision files mean concurrent epics never conflict here.
- **Reverse** a decision: the new file names what it supersedes, and the old file gets a
  superseding note pointing forward (never silently contradict it).
- Entries record the decision and its **why**; as-built behavior belongs to the owning
  system-state doc (link to it).
- Files dated before 2026-06-07 were originally undated; their dates were recovered from git
  history.

## Index (newest first)

- [2026-07-12 — Q&A owner-testing gaps](2026-07-12-qa-owner-testing-gaps.md) — Q&A regains its own inbox badge; escalation is deterministic-first (ingest-time red-flag lexicon, LLM layered later); retrieval grounds on the title; draft provenance is a structured sources object.
- [2026-07-12 — Memory-surface refinements](2026-07-12-memory-surface-refinements.md) — Today tab → Recent (time buckets, needs-input stays inline); Patients tab is a light local filter (the finder is the deep search); grouped attention cards name their target and arm a guided review state.
- [2026-07-12 — Two-layer safety flag](2026-07-12-two-layer-safety-flag.md) — flags carry a normalized `label` + verbatim `text` evidence; additive (no output-version bump); reconcile/rejection keys stay text-based; the strip auto-expands on a new unacknowledged flag signature.
- [2026-07-12 — Report-history hardening](2026-07-12-report-history-hardening.md) — restore is a full redo transition; a deterministic (no-LLM) safety-loss diff confirms before any rollback drops safety content; de-effect is soft-delete-only — media is never destroyed.
- [2026-07-11 — UI-review refinements](2026-07-11-ui-review-refinements.md) — en clock is 24-hour everywhere (one `Intl` seam); one `attentionBadgeCount` feeds bell + chip (partially superseded: Q&A got its badge back).
- [2026-07-10 — Model-comparison verdict](2026-07-10-model-comparison-verdict.md) — keep the incumbent model split (nano synthesis/reconcile + flash-lite elsewhere); mid bracket rejected at ~3.5× cost; fixtures live in `apps/ai_engine/eval/model_compare/`.
- [2026-07-10 — Compressed canonical audio](2026-07-10-compressed-canonical-audio.md) — canonical stored audio is MP3 32 kbps 16 kHz mono; the worker sends stored bytes directly to the gateway; no bulk migration — readers key off `mime_type`.
- [2026-07-10 — Eval gates vote majority-of-N](2026-07-10-eval-gates-majority-vote.md) — `EVAL_VOTES=N` majority voting on failing cases (`=3` is the standard gate run); every prompt-wording change bumps `PROMPT_VERSION` + its pinned hash in the same commit.
- [2026-07-09 — Synthesis-context restructure + treatment status](2026-07-09-synthesis-context-restructure.md) — stable-prefix context serialization: new fields APPEND to the volatile tail, never mid-stable (it moves the prefix-cache boundary); `planned` never counts as `performed` (choose `performed_` vs `effective_treatments` deliberately); capture jobs get identity-minimal context.
- [2026-07-08 — Treatment-row actions](2026-07-08-treatment-row-actions.md) — a row has Edit + source only (never re-add Fix-at-source to rows); action chips are chrome (`t()`); no `prefers-color-scheme` — the app is single-theme until a real theming pass.
- [2026-07-08 — Batch-2 regression fixes](2026-07-08-batch2-regression-fixes.md) — `report_language` is seeded at sign-up (never NULL for new tenants); treatment rows render a technique-attribute whitelist (extend `TECHNIQUE_ATTRIBUTE_KEYS`, never render every attribute).
- [2026-07-06 — Session-surface layout diet + `edit` as human overlay](2026-07-06-session-surface-layout-diet.md) — the `edit` intent is a human-authored overlay, never an AI intent (a field correction is an overlay write, not a re-synthesis); the patient strip is the session shell — new chrome goes inside its expansion.
- [2026-07-06 — Identity & assignment correctness](2026-07-06-identity-assignment-correctness.md) — INV-SILENT (no success-shaped silence), INV-LOCK (serialize `extracted_metadata`), INV-INVALIDATE (state changes re-evaluate dependents); the lattice resolves in `_resolve_capture_identity`.
- [2026-07-06 — Synthesis apply / user-state hardening](2026-07-06-synthesis-apply-hardening.md) — `apply_active_patient_assignment` is THE chokepoint for patient changes; `report_version` cache is patient-scoped; freshness comes from the job-START snapshot; an overlay edit is parked (never destroyed); reconcile can never hide a distinct allergy.
- [2026-07-05 — Cross-visit projection invariants](2026-07-05-cross-visit-projection-invariants.md) — memory freshness stamps from the build-START inputs snapshot; a patient change fans out to every projection that quoted the visit (shares auto-revoke); the memory read path never fabricates content.
- [2026-07-05 — Patient Q&A hardening](2026-07-05-patient-qa-hardening.md) — an unappliable voice edit fails visibly; drafts are optimistically locked on `draft_job_id`; cross-patient isolation is defence-in-depth; qa jobs are metered/pausable and the public ask is throttled; re-opening a revoked thread rotates its token.
- [2026-07-05 — Treatment overlay + synthesis schema-v2](2026-07-05-treatment-overlay-schema-v2.md) — stable treatment identity is a deterministic content-anchored `treatmentKey`, never an LLM-emitted id; the overlay folds via `effective_treatments()` (the only treatments any projection reads); corrections escalate the next synthesis.
- [2026-07-05 — Q&A knowledge: pgvector, ChromaDB rejected](2026-07-05-qa-knowledge-pgvector.md) — pgvector inside the existing Postgres (dimensionless column, no new service); backend embeds directly — the one backend AI-gateway call; blank config means deterministic lexical-only retrieval.
- [2026-07-04 — Encounter chrome noun is per-vertical](2026-07-04-encounter-chrome-noun.md) — aesthetics chrome says **visit**, therapy says **session**; the object/code stays `session`; never coin `session` chrome on aesthetics surfaces.
- [2026-07-04 — Synthesis dispatch: queue-collapse, no debounce](2026-07-04-synthesis-dispatch-queue-collapse.md) — single-flight per session + at most one pending job (a burst of N captures costs ≤ 2 runs); cache-hit restore before dispatch; the sweep is a recovery catch-up, not a timer.
- [2026-07-04 — One router module per domain](2026-07-04-router-module-per-domain.md) — `main.py` is wiring-only; new endpoints go in the matching `app/<domain>_api.py` + per-domain schemas; the route surface is snapshot-guarded.
- [2026-07-04 — AI-engine pipeline hardening](2026-07-04-ai-engine-pipeline-hardening.md) — typed worker-local contracts (never shared with backend) + versioned hash-pinned prompts; structured outputs behind a kill-switch; type-based retry taxonomy; escalation is config-driven.
- [2026-07-04 — Matching seam runs on the transcription model](2026-07-04-matching-seam-transcription-model.md) — the matching seam is a by-product of transcription (flash-lite class); the `m02` near-miss stays a knownGap; the deterministic backend gate — never the model — is the safety net.
- [2026-06-20 — Report sharing and recall](2026-06-20-report-sharing-recall.md) — one report, curated patient subset withheld server-side; brands off by default, lot numbers always withheld from shares; an unconfirmed carried-forward dose gates completeness; lot-recall matching is exact-only.
- [2026-06-14 — Therapy slice 1, beyond the plan](2026-06-14-therapy-slice1-beyond-plan.md) — the as-built therapy record (shared design system, federated caseloads, vertical-agnostic prompts); **AI model selection is NOT a user setting**; single-recording cap; the fair-use $ budget stays internal.
- [2026-06-07 — Intelligence-layer simplification](2026-06-07-intelligence-layer-simplification.md) — patient matching is tier-neutral; the deterministic report rebuild is the always-current baseline (Pro LLM synthesis refines it); completion is auto-derived — no manual verify gate; per-task model config.
- [2026-06-06 — Entity model: Patient universal](2026-06-06-entity-model-patient-universal.md) — `Patient` is universal and never abstracted; the Encounter generalizes by vertical (`tenant.vertical`, `encounterLabel` derived — never hardcoded).
- [2026-06-03 — Intent-driven intelligence layer](2026-06-03-intent-driven-intelligence-layer.md) — capture intelligence is typed intents applied non-destructively, reversibly, capture-attributed (the contract lives in `intelligence-layer.md`).
- [2026-05-22 — Structured report model owns content](2026-05-22-structured-report-model.md) — report body lives in `sessions.report_model`; AI-generated text is never the source of truth for patient demographics.
- [2026-05-20 — Continuously evolving session contracts](2026-05-20-evolving-session-contracts.md) — sessions are draft-from-first-capture and editable across all states; stable frontend contracts (`report`/`summaries`/`findings`/`processingStatus`).
- [2026-05-19 — UX docs are the behavior map](2026-05-19-ux-docs-behavior-map.md) — `docs/ux/` describes currently implemented user-facing behavior; update it with user-facing changes; never duplicate API schemas there.
- [2026-05-17 — AI engine owns capture processing](2026-05-17-ai-engine-owns-capture-processing.md) — the backend produces named Celery tasks; `apps/ai_engine` owns execution and reports back via internal HTTP only — no shared imports, no direct DB writes.
