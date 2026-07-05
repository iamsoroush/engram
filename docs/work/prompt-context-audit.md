# Prompt-context & cache-conformance audit (all AI jobs)

**Status: audit findings + follow-up plan — no code changed.** Audited on `main` (2026-07-05).
Parallel agents are editing prompts in worktrees; treat every recommendation here as a follow-up
work item, re-verified against the file at implementation time. Every prompt change is
**eval-gated** (CLAUDE.md §4): run `apps/ai_engine/eval/run_all.py` and do not regress.

Scope: the 8 jobs' prompt builders (`apps/ai_engine/ai_engine/prompts/*.py`), call sites
(`apps/ai_engine/ai_engine/jobs/*.py`), and backend payload builders
(`apps/backend/app/services/ai_jobs/context.py`, `ai_jobs/worker.py`, `session_processing.py`,
`qa.py`, `patient_memory_intelligence.py`, `ai_jobs/orchestration.py`).

## How caching actually applies here (baseline facts)

- Both providers cache on **exact byte-prefix matching** (OpenAI: automatic, ≥1024-token prefix;
  Gemini implicit: same idea, ~1024–2048-token minimum depending on model). First divergent byte
  ends the cached region; everything after is full price. Cache TTL is short (minutes), so only
  **rapid re-calls** benefit.
- Every job sends **one single user message** (prompt text first, then audio/image part where
  multimodal). There is no system message anywhere. That is fine for prefix caching (text precedes
  the variable media bytes) but means instructions and variable context share one string.
- Every prompt ends with a `json.dumps(context, sort_keys=True)` dump (except `safety_reconcile`,
  which dumps two lists without `sort_keys`). `sort_keys=True` makes **key order** deterministic —
  but alphabetical order **interleaves volatile and stable keys**, and **list order** still leaks
  backend nondeterminism through.
- `response_format` json_schema participates in the cache key. All schemas are module-level Python
  dict literals (insertion-ordered, byte-stable per process) — **conformant**; only deliberate
  schema version bumps invalidate, which is fine.
- Measured static instruction prefixes (chars/3.7 ≈ tokens, aesthetics domain, fa):

| job | total prompt (empty ctx) | static instruction prefix | ≥1024 floor? |
|---|---|---|---|
| synthesis | ~2 614 | **~2 413** | yes — only job whose instructions alone cache |
| transcription | ~992 | ~803 | no (needs stable ctx head to cross) |
| caption | ~991 | ~806 | no |
| patient_memory | ~590 | ~585 | no |
| qa_draft | ~458 | ~415 | no |
| safety_reconcile | ~377 | ~364 | no |
| qa_revise | ~206 | ~179 | no |

Consequence: **synthesis is where cache-layout work pays**; queue-collapse dispatch
(`reports.py` — dispatch on every settle, collapse to one pending job) makes same-session re-runs
land minutes apart, inside provider TTL. Most other jobs are one-shot per input or spaced beyond
TTL (memory rebuilds gate on ~30-min quiescence), so their cache upside is small; their findings
below are mostly **relevance/noise** findings.

---

## 1. Transcription + intents (`prompts/transcription.py`, `jobs/capture_audio.py`, `ai_jobs/context.py`)

Message: one user message, `[text prompt, input_audio]`. Structured `response_format`. Prompt =
configured base (skipped when default) → instruction block → static JSON shape → `Tenant-scoped
transcription context:` + sorted dump. Sorted context key order:
`assignedPatient, clinic, domain, patientSummarizedHistory, preferredLanguage, previousTranscripts, schemaVersion, session, textNotes`.

| context in | source | verdict |
|---|---|---|
| `domain` (label + vocabulary) | `verticals.domain_descriptor` | keep — tenant-stable, drives vocab hint |
| `preferredLanguage` | tenant config | keep — drives language directive |
| `assignedPatient` — displayName, legalFirst/Last, **dateOfBirth, sex, phone, email, nationalId** | `patient_information_from_assignment` | **bias risk / over-scoped.** The prompt's stated use is "spell/transliterate a name actually spoken". Names (+ alternates) serve that; **nationalId/phone/DOB do not** — they invite the model to "confirm" a half-heard digit string from context (the exact failure the guard sentence tries to forbid). Trim to name fields only. |
| `patientSummarizedHistory` | raw `patient.notes`, **unbounded** | flag — token waste + mild content bias; not needed for verbatim transcription. Cap hard or drop. |
| `session` block — id, tenantId, status, title, **summary, createdAt/updatedAt/capturedAt** | session row | noise + churn — `summary` is prior AI output (bias toward last visit's story); `updatedAt` changes every call. ids/timestamps can't help transcription. Drop all but `title`. |
| `previousTranscripts[-5:]` (id, capturedAt, text) | earlier audio captures | keep — legit continuity/name-spelling aid, bounded. Note the `[-5:]` window **rotates** after 5, shifting prefix bytes. |
| `textNotes[-10:]` | note captures | keep, bounded |
| `clinic.name/information/assumptions` | report template | mostly noise — `information` is boilerplate ("Clinical memory report"); assumptions line duplicates the domain label. Slim to name. |

**Bias audit (the misheard-name question):** the model receives exactly one roster name — the
assigned patient's — plus explicit counter-instructions ("never copy the patient's name from
context…, both MUST be null when no name is spoken"). That is the right design *shape*
(spelling aid, not roster matching), and `transcription_eval.py` has the counter-cases; the
residual risk is name-snapping toward the assigned patient on ambiguous audio, and the
gratuitous nationalId/phone/DOB widen that risk for zero benefit.

**Cache:** first variable byte across captures in the same session = inside `previousTranscripts`
(grows per capture), or `assignedPatient` when assignment lands mid-visit. Stable head
(instructions ~800 tok + assignedPatient/clinic/domain/history) sits **around** the 1024 floor —
marginal. Audio bytes follow all text: correct ordering. Low priority: per-clip transcription is
dominated by audio tokens anyway.

## 2. Caption (`prompts/caption.py`, `jobs/capture_photo.py`, `ai_jobs/context.py`)

Message: one user message, `[text prompt, image_url]`. Product-label shots trigger a second pass at
`detail:high` with a **byte-identical text prompt** — good, the text prefix is shared across the
two passes (though at ~806 tok it is below the OpenAI floor).

| context in | source | verdict |
|---|---|---|
| `domain` (label + captionFindings) | descriptor | keep — findings hint is the useful part |
| `preferredLanguage` | tenant config | keep |
| `assignedPatient` (full identity incl. nationalId/phone/DOB) | assignment | **noise + leak surface.** The prompt forbids inventing identity and never uses it; an objective describer has no use for a name. Drop entirely. |
| `captureType` | capture | noise — always `photo` on this path |
| `clinic` | template | noise (boilerplate) — slim to name or drop |
| visit stated purpose / session title | **absent** | **deliberately absent — keep it that way.** Caption is a neutral extractor (objective stand-in, never an assessment); feeding the visit's purpose would prime expected findings. Do not "fix". |

Cache: single-shot per image; only the label re-read reuses the prefix. No action beyond noise
trimming.

## 3. Note passthrough (`jobs/capture_note.py`) — skipped

No gateway call, no prompt. Conforms by definition.

## 4. Session synthesis (`prompts/synthesis.py`, `jobs/session_synthesis.py`, `session_processing.py`, `worker.py`)

The multi-call job that the §3.4.3 cache design targets: re-synthesized on every settle
(queue-collapse), re-runs minutes apart, prompt is the largest in the system (instructions ~2.4k
tok + context that includes the full prior report). Message: one user message (text only —
photos enter as caption text), json_schema `response_format` (byte-stable), optional
`reasoning_effort`.

Sorted context key order (first byte of each key's value is where divergence can start):
`aftercareTemplates, assignedPatient, captures, changeset, clinic, domain, patientSafetyFlags, patientSummarizedHistory, priorDraftTreatments, priorReportModel, rawReportTemplate, referencePriorVisitTreatments, reportLanguage, schemaVersion, session`.

| context in | source | verdict |
|---|---|---|
| `aftercareTemplates` [{id,name,procedureType,body}] | `worker._aftercare_templates_for_synthesis` | **needed** (the prompt's aftercare-selection contract) but **the query has no ORDER BY** — Postgres may return the rows in different orders run-to-run, and list order survives `sort_keys=True`. This is the *first key in the dump*: nondeterministic ordering here can kill the cached prefix at its very first variable byte, even for a byte-identical session. One-line fix (`.order_by(created_at, id)`). |
| `assignedPatient` (full identity) | assignment | keep name; nationalId/phone/email/DOB are report-header data the **backend** injects at render time ("backend owns patient-information injection") — noise here. |
| `captures` grouped `{audio, photos, text}` | `build_session_processing_input` | content is the task substrate — keep. **Grouping breaks append ordering**: a new photo lands mid-JSON (inside `photos`, before `text`), so run N+1 does not extend run N's byte prefix. Per-capture `artifactUrl`/`s3Url`/`status` and audio `detectedPatient`+`patientInformation` are noise (synthesis never assigns patients; the renderer resolves images from `captureId`). |
| `changeset` (added/removedCaptureIds) | vs last synthesis | keep (drives the targeted update) — but it **differs on every run by construction**; alphabetically it sits at position 4, ahead of five stable keys. Move to the tail. |
| `clinic` | template | slim (boilerplate) |
| `domain` (incl. areaCodes) | descriptor | keep — tenant-stable |
| `patientSafetyFlags` | `patient_safety_flags_payload` | keep (reconcile input), stable order (insertion-deduped) |
| `patientSummarizedHistory` | raw `patient.notes` unbounded | cap; prior-visit grounding already comes from `referencePriorVisitTreatments` |
| `priorDraftTreatments`, `priorReportModel` | this session's last output | keep (update discipline + priorKey rebinding) — **changes every run**; must be last-ish. `priorReportModel` is the single largest re-fed blob. |
| `rawReportTemplate` | `report_template_payload` | **noise** — a `{{ patient_information }}/{{ body }}` skeleton; the section contract comes from the fixed `SYNTHESIS_SECTIONS` in the instructions. Drop from the LLM context. |
| `referencePriorVisitTreatments` (≤12, keyed) | prior visit | keep — bounded, powers carry-forward; ordering is stored-list order (stable) |
| `reportLanguage` | tenant | keep (also interpolated in instructions) |
| `session` block incl. **`metadata: session.extracted_metadata` — the ENTIRE previous extracted metadata** | session row | **worst offender.** This re-feeds the model its own full prior output *a second time* (progressive_report body, summaries, findings, treatments, safety flags…) alongside `priorReportModel`, plus `processing_status`/`generated_at` **timestamps that change every run** — token waste, self-referential bias, and guaranteed byte churn. Also `session.summary` (prior AI output) and `updatedAt`. Keep `id`/`title` at most. |

**First variable byte, today, for run N+1 of the same session:** best case the first byte of
`changeset` (~after instructions + aftercareTemplates + assignedPatient + captures ≈ several
thousand tokens cached — *if* aftercareTemplates ordering happens to repeat); typical case the
first changed entry inside `captures`; worst case byte 0 of the context dump when the unordered
aftercare query flips row order. Everything after divergence — including the stable
`clinic/domain/rawReportTemplate/referencePriorVisitTreatments` keys that alphabetically follow
`changeset` — is re-priced every run.

**Target layout** (matches `docs/work/ai-engine-refactor-plan.md` §3.4.3): emit the context as
explicitly ordered segments instead of one sorted dump —
1. instructions + schema framing (already first, stable per tenant),
2. clinic-stable block: `domain, clinic, reportLanguage, aftercareTemplates` (deterministically ordered),
3. patient/visit-stable block: `assignedPatient (name), patientSummarizedHistory (capped), patientSafetyFlags, referencePriorVisitTreatments`,
4. `captures` as ONE flat list ordered by `capturedAt/created_at` (append-only across runs),
5. volatile tail: `changeset, priorDraftTreatments, priorReportModel` — ideally in a **second user
   message** so the boundary is explicit.

Then run N+1's prompt extends run N's byte prefix through segments 1–3 plus captures up to the
newly added one — the §3.4.3 "~10× cheaper re-fed input" claim becomes real instead of aspirational.

## 5. Safety reconcile (`prompts/safety_reconcile.py`, `jobs/safety_reconcile.py`)

One extra call inside each synthesis completion (when ≥2 flags). Static instructions ~364 tok +
`EXISTING flags:` / `NEW flags:` JSON lists (no `sort_keys`, but rows are built with fixed literal
key order — deterministic). Selection-only contract; json_schema stable.

- **Relevance: exactly sufficient by design** — flags in, keys+status out; deliberately isolated
  from the free-writing synthesis prompt (D7). No missing context, no noise.
- **Cache: below the floor and single-shot per synthesis run — not worth layout work.** The real
  saving is the §3.4.3 item 4 **memoization** (same candidate-flag set re-reconciled across a
  session's repeated synthesis runs → reuse the stored verdict, skip the call entirely). That
  dominates anything caching could do here.

## 6. Patient memory (`prompts/patient_memory.py`, `jobs/patient_memory.py`, `patient_memory_intelligence.py`, `orchestration.py`)

Message: one user message, json_schema. Prompt = framing → instructions (language directive
tenant-stable) → static JSON shape → `Patient context:` + sorted dump of `patient` only. Sorted
key order: `displayName, firstSeen, priorMemory, sessions, visitCount`.

| context in | source | verdict |
|---|---|---|
| `displayName` | patient | **contradiction/noise** — the prompt forbids using the name in any field; Persian pronouns are genderless, so the name buys nothing. Drop (or keep for register only, consciously). |
| `firstSeen`, `visitCount` | sessions | keep — cheap grounding |
| `priorMemory` {summary, history} | last build's output | keep — the incremental anchor |
| `sessions[:8]` briefs {date, captureCount, latestType, summary, treatments[:8] (overlaid — clinician-corrected doses, AES-1101)} | `_session_brief` | keep — this is the right shape: distilled briefs, not raw transcripts; overlay-read is the lot-recall safety case |
| `language`, `domain` | tenant | keep (read into directives, not dumped) |

**Incremental priorMemory vs windowed rebuild: keep the incremental design.** Cost stays ~flat as
visits grow (8 briefs + prior memory), and old visits survive through the prior memory — a
windowed rebuild would either forget or re-feed everything. Its known weakness (drift/error
accumulation in the prior memory across many rebuilds) is a quality question for the eval set,
not a context-design flaw.

**Cache: structurally 0% reusable across rebuilds and *that is acceptable*.** First variable byte
= `displayName` at ~585 tok (below floor); `priorMemory` (changes every build) precedes the bulky
`sessions`; sessions are **newest-first**, so run N+1 diverges at `sessions[0]`. But rebuilds gate
on ~30-min quiescence / staleness-on-read — beyond provider TTL — so reordering (oldest-first
sessions, priorMemory last) buys real cache hits only for rapid successive rebuilds, which the
per-patient dedup already suppresses. File as nice-to-have, not a priority.

## 7. qa_draft (`prompts/qa_draft.py`, `jobs/qa_draft.py`, `qa.py`)

Message: one user message, **plain text out (no response_format)**. Section order: framing →
instructions (**`doctorName` interpolated mid-paragraph**) → exemplar rules (static, only when
exemplars exist) → exemplars dump → patient question → patientContext → priorAnswers.

| context in | source | verdict |
|---|---|---|
| `patientQuestion` | the pending message body | keep |
| `patientContext` {displayName, memorySummary, history, recentVisitSummaries[3]} | `_patient_qa_context` | keep displayName (greeting) + memorySummary + summaries; `history` = raw unbounded `patient.notes` — cap. |
| `priorAnswers` (≤8 sent Q&A pairs, doctor-scoped) | `_prior_doctor_answers` | keep — the tone anchor; bounded, deterministic order (created_at desc). |
| `retrievedExemplars` (top-3: template + indexed replies) | `qa_retrieval.retrieve` | keep — v2's grounding; priority rules in-prompt are correct (patient context wins, no cross-patient numbers, safety precedence). |
| `doctorName`, `clinicName` | thread/tenant | doctorName used (sign-off); `clinicName` is passed in the payload but **never read by the prompt** — dead field. |
| **the aftercare actually given to THIS patient** | **absent** | **top missing-context finding.** The prompt orders: "reference the aftercare already given" and "never contradict the aftercare THIS patient was given" — but the context contains no aftercare at all unless it leaked into a visit summary. The grounding for the prompt's own safety rule is missing; the model must guess or generalize. Feed the last visit's effective aftercare (dictated text + applied template names/bodies from `aftercareSelections`), bounded. |
| **prior messages of THIS thread** | **absent** | flag — a follow-up question is drafted without the thread's earlier Q→A exchange (priorAnswers is doctor-wide, not thread-scoped). Add the thread's prior sent exchange (bounded, e.g. last 2 turns). |

**Cache:** first variable byte = `doctorName` inside the instruction paragraph (~350–400 tok in),
ahead of the *static* exemplar-rules block — so even the static rules never share a prefix across
doctors. Trivial fix when next touching this prompt: keep instructions fully static ("Sign off
with the doctor's name given below"), move the name into the variable tail. Still below the
1024 floor for clinic-level reuse unless priorAnswers (per-doctor-stable) is hoisted ahead of the
per-question content — worth doing opportunistically, not urgently (drafts are sporadic; TTL
misses likely).

## 8. qa_revise (`prompts/qa_revise.py`, `jobs/qa_revise.py`, `qa.py`)

Message: one user message `[text, input_audio(voice note)]`, json_schema (`{mode, reply}`).
Context: patientQuestion → currentDraft → patientContext → priorAnswers. It **does** receive the
patient context (question answered), plus the draft and the voice note — sufficient.

- `priorAnswers` (8 Q&A pairs) is **noise here**: the task is classify-revise-vs-replace + apply
  the doctor's own spoken instruction; tone comes from `currentDraft`. Worth an A/B in the eval
  before removing, but expected pure token saving. (For a `replace` dictation it could help tone —
  if kept, 2–3 pairs suffice.)
- Cache: one-shot per voice edit, ~179-tok static prefix — no cache story; no action.

---

## Ranked recommendations

Ordering: (impact × certainty) / effort. Every item touching a `prompts/*.py` module or a payload
list *ordering* is **eval-gated** — run `apps/ai_engine/eval/run_all.py`; synthesis items ride
`report_sections_eval` + `treatments_eval` + `aftercare_conflict_eval` + `safety_flags_eval`,
transcription items ride `transcription_eval`, qa items ride `qa_draft_eval`/`qa_revise_eval`
(note: `qa_revise` scored clips r01–r10 still pending per `docs/ai_engine/evals.md`). Pure
payload-field *removals* still change prompt bytes (the dump shrinks) — same gate.

1. **Synthesis: stop re-feeding `session.extracted_metadata`.** Drop `session.metadata` (and
   `session.summary`, `updatedAt`) from `build_session_processing_input`'s `session` block —
   `apps/backend/app/services/session_processing.py`. Impact: removes the largest pure-noise blob
   (the model's own prior full output duplicated next to `priorReportModel`, plus per-run
   timestamp churn that breaks byte-stability); cuts input cost on *every* synthesis run and
   removes a self-referential bias channel. Effort: small. Risk: verify the worker's legacy
   deterministic path doesn't read it (it reads `sessionProcessingContext.captures`, not
   `session.metadata`). Evals: synthesis suite, expect neutral-or-better.
2. **Synthesis: deterministic `aftercareTemplates` ordering.** Add `.order_by(created_at, id)` in
   `_aftercare_templates_for_synthesis` — `apps/backend/app/services/ai_jobs/worker.py`. Impact:
   removes a run-to-run nondeterminism sitting at the FIRST key of the context dump (cache-killer
   at byte ~0 of the variable region) and makes template presentation order stable for the model.
   Effort: one line. Evals: none affected (evals pass literal lists).
3. **Synthesis: stable-prefix segment layout** (the §3.4.3 item). Replace the single
   `json.dumps(context, sort_keys=True)` tail in `apps/ai_engine/ai_engine/prompts/synthesis.py`
   with explicitly ordered segments — clinic-stable → patient-stable → captures (ONE flat
   chronological append-ordered list) → volatile tail (`changeset`, `priorDraftTreatments`,
   `priorReportModel`) last, ideally as a second user message; drop `rawReportTemplate` and the
   noise capture fields (`artifactUrl`, `s3Url`, `detectedPatient`, `patientInformation`) on the
   way. Impact: run N+1 shares a multi-thousand-token byte prefix with run N → ~10× cheaper re-fed
   input on the dominant job; also a modest quality win (rules → stable facts → deltas reads
   better than alphabetical interleave). Effort: medium (prompt module + `worker.py`/
   `session_processing.py` context assembly + eval payload fixtures). Evals: full synthesis suite;
   verify via the meter's `usage` records (cached-token counts) in staging.
4. **qa_draft: feed the aftercare actually given.** Extend `_patient_qa_context` (or a sibling
   field) in `apps/backend/app/services/qa.py` with the most recent visit's effective aftercare —
   dictated aftercare prose + applied template names/bodies (bounded, e.g. last visit only) — and
   reference it explicitly in `prompts/qa_draft.py`. Impact: quality/safety — grounds the prompt's
   own "never contradict the aftercare THIS patient was given" rule instead of leaving it
   unenforceable. Effort: small-medium. Evals: `qa_draft_eval` + add a golden case (aftercare
   present in context, reply must cite it, not invent) — **consult the user on golden-set
   scenarios first** per CLAUDE.md §4.
5. **Transcription/caption: trim identity to what the task uses.** In
   `apps/backend/app/services/ai_jobs/context.py`, send only name fields (displayName + legal
   names) for `assignedPatient` in the transcription context (drop nationalId/phone/email/DOB/sex)
   and drop `assignedPatient` from the caption context entirely; cap `patientSummarizedHistory`;
   slim `clinic`/drop `session.summary`+timestamps. Impact: closes the "confirm a half-heard
   national ID from context" bias hole, removes identity leakage into caption calls, saves tokens
   on every capture. Effort: small. Evals: `transcription_eval` (its no-name-in-context
   counter-cases must stay green), `caption_eval`.
6. **qa_draft: static instructions + thread history.** Move `doctorName` out of the instruction
   paragraph into the variable tail ("sign off with the name given below"), reorder to
   rules → doctor-stable (priorAnswers) → patient block → exemplars → question last, drop the
   unread `clinicName` payload field, and add the thread's prior exchange (bounded) for follow-up
   questions. Impact: small cost win, real quality win on follow-ups. Effort: small-medium. Evals:
   `qa_draft_eval` (+ a follow-up-question golden case — consult user).
7. **qa_revise: shrink `priorAnswers`.** Cut to ≤2 pairs (or drop) in `qa_revise_worker_payload` —
   `apps/backend/app/services/qa.py`. Impact: pure token saving on every voice edit. Effort: tiny.
   Evals: `qa_revise_eval` harness (scored clips pending — gate on the parser/self-tests +
   re-score when r01–r10 land).
8. **Patient memory: drop `displayName`; optionally append-order sessions.** Remove the field the
   prompt forbids using (`patient_memory_intelligence.build_patient_memory_job_input`); if ever
   optimizing further, flip `sessions` to oldest-first and move `priorMemory` after them — but
   rebuild spacing (quiescence ≥ TTL) means cache reuse is mostly theoretical; the **incremental
   priorMemory design is the right one — keep it** over any windowed-rebuild alternative. Effort:
   tiny. Evals: `patient_memory_eval`.
9. **Safety reconcile: memoize identical candidate sets** (already specified as
   `ai-engine-refactor-plan.md` §3.4.3 item 4 — key over the exact candidate-flag set, reuse the
   stored verdict across a session's repeated synthesis runs). No prompt change; skips whole calls,
   which beats any caching at its 364-token size. Evals: `safety_reconcile_eval` unaffected.
10. **Transcription context window semantics (opportunistic).** The `previousTranscripts[-5:]`
    rotation breaks append ordering once a session exceeds 5 audio captures and the `session`
    block's `updatedAt` churns bytes; if item 5 is done, also drop the dead timestamps. Below the
    cache floor on its own — bundle with item 5, don't do separately.

Non-goals confirmed by this audit: do **not** give caption the visit's purpose (neutral-extractor
contract, deliberate); do **not** merge safety-reconcile into the synthesis prompt (D7 isolation is
correct); do **not** replace incremental patient memory with windowed rebuilds; note passthrough
stays LLM-free.
