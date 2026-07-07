# AI-engine refactor plan — code structure + pipeline design

**Status:** reviewed by the user 2026-07-04 — decisions recorded in the final section; not started.
Plan only — no source changes made.
**Scope:** `apps/ai_engine` (the worker) + AI-pipeline design. Peer of the backend
structural-refactor (routers/schemas split — landed; see
[technical-decisions.md](../technical-decisions.md) "One Router Module Per Domain" and
[backend/README.md](../backend/README.md) "Code layout"), which owns `apps/backend/app/services/ai_jobs/`
dispatch-side structure, and the frontend seam architecture ([frontend/overview.md](../frontend/overview.md#composition-root--seams),
folded from the completed frontend-refactor plan). Seam ownership for cross-cutting changes: §5.
**Fold destinations (when built):** module map + prompt-versioning + structured-output policy →
`docs/ai_engine/processing.md` and `docs/ai_engine/README.md`; treatment-key + overlay-extension
decisions → `docs/architecture/pipeline-versioning.md`; dated decisions (debounce-on, key strategy,
no-streaming, reconcile-stays-separate) → `docs/technical-decisions.md`; scorecard provenance
(promptVersion) → `docs/ai_engine/evals.md`; updated `_MeteredClient` file path + debounce status →
`docs/business/ai-usage-limits.md`. Then delete this doc and rewire links.

Ground truth consulted: `docs/ai_engine/{README,processing,evals}.md`,
`docs/architecture/pipeline-versioning.md`, `docs/business/ai-usage-limits.md`,
`apps/ai_engine/ai_engine/{processing.py,tasks.py,config.py}`, backend
`services/ai_jobs/` + `services/report_versions.py`, `docs/work/ux-epic-*.md`,
`apps/frontend/tests/e2e-stack/`.

---

## 1. Baseline

| Area | Observation |
|---|---|
| `ai_engine/processing.py` | **2,675 lines** holding all 8 job bodies + every shared concern: gateway client + `_MeteredClient` + usage sink, `BackendClient`, ffmpeg/ffprobe audio, image downscale, digit/script normalization, `domain_framing`, all prompt builders, all parsers/validators, all fixture fallbacks. The single refactor target. |
| `tasks.py` (147) | 8 Celery task names (`ai_engine.process_audio_capture`, `_text_`, `_image_`, `process_session`, `process_patient_memory`, `process_qa_draft`, `process_qa_revise`, `recover_pending_ai_jobs`) + the shared retry wrapper (`run_task_with_retries`, `retry_reason_for_exception`). **Task names are the deployment contract** — in-flight queued jobs survive a deploy only if names are byte-identical. |
| Structured outputs | Only **2 of 7** gateway call sites are schema-enforced (`response_format: json_schema`): synthesis + safety-reconcile. Transcription, caption, patient memory, `qa_draft`, `qa_revise` parse free text with fence-stripping regex + tolerant `parse_*` functions. |
| Contracts | Output shapes are dict-shaping (`_clean_*`, `normalize_*`); one versioned schema constant exists (`SESSION_SYNTHESIS_OUTPUT_VERSION`); other jobs have no explicit output version. Treatments are an **unkeyed** JSON array. |
| Tests | `apps/ai_engine/tests/` — 6 gateway-less unit files (enrichment, memory, qa_draft, synthesis, retry-reason, transcription parsing). Eval suite: `eval/run_all.py`, 9 modules (`_common.py` harness). `qa_draft`/`qa_revise` have **no evals** (known debt). |
| Fixture seams (load-bearing) | `TEST_CAPTURE_TEXT_BY_FILENAME`, `is_fixture_capture`/`is_expected_test_fixture`, `expected_test_structured_report`, the synthesis **skip sentinel** (`session_synthesis_skip_output`), memory/QA `deterministicFallback`, blank-caption fallback. The merge-gating real-stack suite (`apps/frontend/tests/e2e-stack/`) drives the pipeline through these seams gateway-less — they must survive byte-for-byte in behavior. |
| Cost profile | Full-session re-synthesis per capture is the dominant cost ($0.0203/visit vs $0.0023 coalesced — [ai-usage-limits.md](../business/ai-usage-limits.md)); `synthesis_debounce_seconds` is implemented but **default 0 = disabled**. |

---

## 2. AXIS 1 — code refactoring of `apps/ai_engine`

### 2.1 Target package layout

Split `processing.py` **by job**, with shared infrastructure in a `core/` package and prompts in
their own versioned modules (§3.3):

```
ai_engine/
  core/
    gateway.py        gateway_settings_for, gateway_client, _MeteredClient, usage sink,
                      resolve_model, resolve_reasoning_effort
    backend_client.py BackendClient (start/complete/progress/retry/fail/recover, file fetch)
    media.py          audio→FLAC (ffmpeg), audio_duration_seconds (ffprobe), image downscale,
                      image_to_data_url
    text.py           digit/script normalization, language directives, JSON fence-strip helper
    domain.py         domain_framing (the vertical-agnostic seam)
    fixtures.py       TEST_CAPTURE_TEXT_BY_FILENAME, is_fixture_capture,
                      expected_test_structured_report, mock_findings, deterministic fallbacks
    errors.py         typed worker exceptions → retry-reason codes (§3.6)
  contracts/          typed output models + per-job OUTPUT_VERSION constants (§2.2)
  prompts/            one module per prompt + _shared.py, each with PROMPT_VERSION (§3.3)
  jobs/
    capture_audio.py      transcription + patient_information + intents
    capture_photo.py      caption + OOC/pairing + product-label re-read
    capture_note.py       passthrough
    session_synthesis.py  session_organize (A↔B contract) + skip sentinel
    safety_reconcile.py   the in-job selection-only reconcile call
    patient_memory.py
    qa_draft.py
    qa_revise.py
  tasks.py            unchanged task names; imports job runners from jobs/
  processing.py       TEMPORARY re-export shim (evals/tests/backend docs import processing.*);
                      deleted in the final increment after imports are rewired
```

Rules: `jobs/*` may import `core/*`, `contracts/*`, `prompts/*` — never each other (the one
exception: `session_synthesis` calls `safety_reconcile`, its in-job second pass). Nothing imports
backend code (boundary rule in `docs/ai_engine/README.md`).

### 2.2 Typed contracts

Replace dict-shaping with typed models (pydantic — already a dependency via `pydantic_settings`) in
`contracts/`, one module per payload family:

- **Synthesis output** (the A↔B contract): `SessionSynthesisOutput`, `TreatmentItem`,
  `AftercareSelection`, `SafetyFlag`, `SectionBlock` — replacing `_clean_synthesis_*`.
- **Capture intelligence**: `StructuredTranscription`, `PatientInformation`, `Intents`
  (`normalize_intents` becomes model validators with the same drop-field-by-field tolerance).
- **Caption**: `CaptionResult` + `PairingAttributes`.
- **Memory / Q&A**: `PatientMemoryOutput` (summary/history/card), `QaDraftOutput`, `QaReviseOutput`.

Generalize the `SESSION_SYNTHESIS_OUTPUT_VERSION` pattern: every job's contract module declares an
`OUTPUT_VERSION = "YYYY-MM-DD.<name>.vN"` and the job embeds it in its output envelope (transcription
already has a documented schema id, `2026-06-03.capture-intelligence.v1` — make it code, not prose).

**Decision — contracts stay worker-local.** The backend keeps validating its side independently
(JSON-over-HTTP is the contract; the `schemaVersion` string is the shared truth). A shared Python
contracts package would couple the two deployables the boundary deliberately keeps apart. Each model
mirrors the *same* tolerance the current parsers have — a typed model must not silently tighten
validation (that would be a behavior change: e.g. malformed intents are dropped per-field, never
fail the transcript).

### 2.3 Sequenced increments (each shippable, each gated)

Per-increment gate: `python -m pytest apps/ai_engine/tests` (or unittest, matching CI) green ·
`eval/run_all.py` no regression where a gateway is reachable · the e2e-stack suite green
(fixture seams intact) · task-name snapshot unchanged.

- **Increment 0 — characterization net.** (a) A unit test snapshotting the **registered Celery task
  names** (the deployment contract). (b) Extend `apps/ai_engine/tests/` to pin the pure seams the
  split leans on and that are thinly covered: `parse_caption_output`, `parse_patient_memory_output`,
  `parse_qa_*`, `parse_safety_reconcile_output`, `normalize_intents` edge cases,
  `session_synthesis_skip_output`, fixture recognition. No production code moves.
- **Increment 1 — extract `core/`.** Gateway+metering, `BackendClient`, media, text, domain,
  fixtures move out; `processing.py` re-exports every public name (evals and tests keep importing
  `ai_engine.processing`). Pure move, no logic edits.
- **Increment 2 — extract `jobs/` one job per commit**, order: note → photo → audio → memory →
  qa_draft → qa_revise → synthesis (+ reconcile). Moving a job body counts as re-implementing it →
  run the eval suite per commit batch. The shim keeps old import paths alive.
- **Increment 3 — typed contracts** (§2.2), swapped in at the parse boundaries one job at a time.
  This is where subtle behavior change is possible — each swap adds table-driven parity tests
  (old parser vs model on the same corpus, including malformed inputs) before deleting the old code.
- **Increment 4 — prompts package** (§3.3 mechanics; content byte-identical in this axis — version
  stamps only, no wording changes).
- **Increment 5 — delete the shim.** Rewire `eval/*` + `tests/*` imports; update the doc references
  to `processing.py` (`docs/ai_engine/processing.md` fixture note, `docs/business/ai-usage-limits.md`
  `_MeteredClient` path); run `scripts/check-doc-links.py`.

---

## 3. AXIS 2 — better AI pipelines

Each item: problem → proposal → cost/latency/quality impact → migration + eval implications.
Recommendations, not surveys; every behavior change here is its own increment, eval-gated.

### 3.1 Model routing

- **Problem.** Routing is one static `{model, reasoningEffort}` per task (`app_config.ai_models` →
  payload `aiModels` → `resolve_model`). No escalation path: a flash-class model that intermittently
  auto-corrects a near-miss name (the `m02` knownGap) or a malformed structured output has no
  "try harder" lever short of globally switching the task to a costlier model.
- **Proposal.** Extend the per-task entry with an optional **escalation tier**:
  `{model, reasoningEffort, escalation: {model?, reasoningEffort?}}`, fired by **two triggers** —
  never speculatively:
  1. **Validation-failure retry (plumbing trigger).** The model's reply fails the output-schema
     validation (§3.2) → the single in-job retry runs on the escalation tier. Failure detection is
     mechanical: the JSON doesn't validate.
  2. **Correction-triggered escalation (user-signal trigger — added in review).** When the user's
     own action tells us the previous output was wrong, the re-run of the affected job escalates to
     the strongest configured model. Concrete signals, all already detectable: an audio capture
     whose `intents` carry an **explicit assignment correcting a prior one** (the "second audio to
     fix the misheard patient name" case → re-run transcription/matching escalated); a
     **Fix-at-source transcript edit** (→ the forced re-synthesis runs escalated); a
     **treatment-overlay field edit** (→ the next synthesis for that session runs escalated). The
     principle generalizes: *a correction is proof the cheap tier failed on this input — spend more
     exactly there.* This also feeds the eval harvest loop (every correction is a candidate golden
     case).
  Do **not** build speculative cheap-first-with-confidence-escalation: it doubles cost on the hard
  cases without a signal. The existing image detail tiers (1280px/`detail:low` → 2048px/
  `detail:high` product-label re-read) already implement the content-triggered pattern and stay
  as-is. Long-audio needs no routing: transcription is priced per-minute and the 20-min cap bounds it.
- **Impact.** Cost ≈ unchanged in steady state (escalation fires only on failures/corrections);
  quality raised precisely where the user demonstrated a miss — the highest-trust place to spend.
- **Migration/eval.** Backward-compatible config shape (bare string and `{model, reasoningEffort}`
  keep working). Correction-signal plumbing is backend-owned (it knows *why* a job re-dispatches —
  add an `escalate: true` hint to the job payload); the worker just resolves the tier. Run the full
  suite under both primary and escalation config; the `m02` knownGap is the acceptance case for the
  transcription/matching path.

### 3.2 Structured outputs everywhere

- **Problem (plainly).** 5 of 7 call sites just *ask* for JSON in the prompt and hope: the model's
  reply is free text that the worker fence-strips and parses tolerantly. When the model returns
  malformed/partial JSON, today's outcome is a retryable failure (audio), a **blank caption**, or a
  deterministic fallback (memory/QA) — i.e. a wasted paid call or silently lost AI value. Only
  synthesis and safety-reconcile currently *enforce* the shape at the API level.
- **Gateway fact (confirmed in review):** the gateway enforces output schema for **both OpenAI and
  Gemini models in the OpenAI-compatible manner** — the worker just sends
  `response_format: json_schema` and treats the gateway as OpenAI regardless of the underlying model.
- **Decision (review): all JSON-emitting jobs use schema-enforced outputs — including transcription.**
  (a) Roll out per task behind the `structuredOutputs` flag, preceded by a **gateway conformance
  test**: for each model family actually configured (OpenAI-class + Gemini-class), send a
  representative schema and assert the response validates — run once per rollout and kept as a
  scheduled check. Transcription (audio input + json_schema) rolls out last, but it is in scope.
  (b) **Retry-on-invalid:** one in-job re-request appending the validation error (and applying the
  §3.1 escalation tier if configured) before falling back to today's paths. (c) Keep the typed
  contracts (§2.2) as the validation layer regardless — schema enforcement is best-effort defense
  in depth; the fence-strip regex dies only after (a) proves out per task.
- **Impact.** Fewer wasted calls and fewer blank captions/fallbacks (cost + latency down on the
  failure tail); no intended quality change to valid outputs.
- **Migration/eval.** Per-task rollout, one increment each, full eval run per task (transcription
  and caption evals cover the risky ones directly). No schema *content* change in this item.

### 3.3 Prompt architecture — auditable, versioned modules

- **Problem.** Prompts are inline f-string builders scattered through `processing.py`; the
  vertical-agnostic rule (`domain_framing`) is convention, and an eval regression cannot be
  attributed to a specific prompt diff — the scorecard doesn't know what prompt produced a run.
- **Proposal.** `ai_engine/prompts/` with one module per prompt (`transcription.py`, `caption.py`,
  `synthesis.py`, `safety_reconcile.py`, `patient_memory.py`, `qa_draft.py`, `qa_revise.py`), each
  exposing `PROMPT_VERSION = "YYYY-MM-DD.<name>.vN"` + `build(context) -> str`. Shared blocks live
  in `prompts/_shared.py`: the vertical-agnostic core (domain framing, neutral fallback), language
  directives, and the cross-job discipline rules (grounding/no-invention, verbatim-original-script,
  native-script/never-romanize) — so a discipline fix lands once, and per-job files hold only
  framing. Enforcement: a unit test pins each version to a hash of its canonically-built prompt —
  editing wording without bumping `PROMPT_VERSION` fails the suite. Every job output envelope gains
  `promptVersion` alongside `generated_by`/model; the eval scorecard records
  `{model, reasoningEffort, promptVersion}` per run, making regressions attributable to prompt diffs.
- **Impact.** Zero runtime cost; pure auditability + safety. Per pipeline-versioning **D1**, cache
  keys still ignore prompt version — provenance is recorded, never keyed on.
- **Migration/eval.** Axis-1 increment 4 lands the mechanics with byte-identical prompt text (eval
  run proves no drift); wording changes forever after are ordinary eval-gated prompt PRs with a
  version bump.

### 3.4 Synthesis cost/latency (the dominant spend)

Four levers, in recommended order:

1. **Queue-collapse dispatch (single-flight + one pending) — final design, decided with the user
   2026-07-04. No timer, no debounce.** Per-capture responsiveness stays; only *redundant queued
   work* is eliminated. A session's synthesis jobs form an ordered per-session pipeline, and every
   job reads the **full current capture set at execution time** — so two invariants implement the
   user's algorithm:
   - **At most one running + one pending synthesis job per session.** A new trigger while a job is
     merely *queued* is a no-op — the queued job will see the new captures when it runs (it reads
     current state). A new trigger while a job is *running* ensures exactly one follow-up pending
     job exists (the running job read the set before this capture landed).
   - Equivalently: "if multiple synthesis jobs are queued for a session, delete them and keep one
     job covering all remaining captures" — collapse-by-supersession rather than delay.
   Result: the first capture synthesizes **immediately** (trust intact); a burst of N captures costs
   ≤ 2 runs (the in-flight one + one collapsed follow-up) instead of N; a single-capture visit has
   zero added latency and zero extra cost. `force=True` (content edits, manual regenerate) keeps
   its meaning. **Owner: backend** (`reports.py` dispatch guard — supersede/no-op logic on the job
   rows; the existing debounce sweep machinery is retired or repurposed as the collapse check).
   Worker and evals unaffected.
   **Cost companion — prompt caching (§3.4.3):** with the stable-prefix prompt layout, the re-fed
   context of a follow-up run hits the provider prompt cache (~10× cheaper input tokens), so even
   per-capture synthesis on non-bursty sessions stays cheap. Measure via the meter's `usage`
   records.
   **Observe before optimizing further — internal cost dashboard (future work):** per-clinic real
   AI cost is already metered (`AiUsageCounter`, micro-dollars, per clinic); a small internal
   admin dashboard over that data shows each clinic's true cost, and only if real numbers show a
   problem do we add further levers. No pre-emptive throttling.
   **Budget-accounting clarification (from review):** metering and caps are already enforced
   **per-clinic** — the clinic's pool is `seats × ai_budget_usd_per_seat`; a heavy user draws from
   the shared pool. The per-seat number is only the pool's *scaling rule*, coherent while pricing
   is per-seat (today's anchor); if pricing ever moves to flat per-clinic, re-base the budget
   derivation in the same change ([pricing.md](../business/pricing.md) owns the price decision).
2. **Cache-hit before dispatch (extend the existing capture-set-hash cache).** Today
   `find_report_version_for_current_set` powers undo/delete restore. Extend: **every** settle
   trigger checks the store before dispatching `session_organize` — a hash hit restores instead of
   re-synthesizing (e.g. edit-then-revert, mark-relevant toggles). Deterministic, no quality risk.
   **Owner: backend** (`reports.py` dispatch guard + `report_versions.py`); this plan supplies the
   invariant: restore must keep applying the overlay (already true).
3. **Prompt-cache-friendly layout, defer true delta synthesis.** Restructure the synthesis prompt as
   a **stable prefix** (rules, schema framing, clinic/template context) + append-ordered captures,
   so OpenAI-compatible prompt caching discounts the re-fed prefix; measure via the `usage` records
   the meter already ships. **True incremental synthesis** (send only the changeset anchored on the
   prior `report_version`) is *deferred*: supersede/correction chains and treatment dedup need the
   full capture set for correctness, the content-addressed cache keys on the full set, and the
   debounce already collapses the N-runs-per-visit problem the delta would chase. Revisit only if
   post-debounce measurements still show synthesis dominating.
4. **Safety-reconcile: no structural change — just skip redundant repeat calls.** (Clarified in
   review.) Today safety-reconcile is a *second, separate* LLM call inside the synthesis job that
   cross-checks candidate safety flags against patient history. The alternative considered — merging
   it into the main synthesis prompt to save a call — is **rejected**: D7 deliberately isolated it
   because a narrow selection-only prompt can't hallucinate new safety text the way a free-writing
   prompt can. The only change proposed: **memoize** — before calling, compute a key over the exact
   candidate-flag set; if that same set was already reconciled earlier in the session (common when
   a session re-synthesizes repeatedly), reuse the stored verdict instead of paying for an identical
   call. A cache lookup, nothing more; the job structure stays as-is.

### 3.5 Streaming — recommendation: no

- **Problem/question.** Would streaming synthesis output into the live report beat the current
  poll-based `Organizing → Updating → complete` UX?
- **Recommendation.** No. The perceived-latency problem is already solved structurally: the
  deterministic baseline renders instantly and synthesis is a quiet refinement. Streaming partial
  JSON would create report states where prose and `treatments[]` (the A↔B atomicity) disagree
  mid-stream, complicate the skip-sentinel/fallback paths, and — once the debounce is on (§3.4.1) —
  synthesis mostly runs *after* the clinician looks away. The existing `progress_job` stage callback
  is the right granularity. Revisit only on a real post-debounce latency complaint.

### 3.6 Fallbacks, parking, retry taxonomy

- **Problem.** `retry_reason_for_exception` classifies by **substring-matching exception messages**
  (`"openai" in message`, `"timeout" in message`) — brittle and unauditable. Malformed structured
  output is indistinguishable from generic `worker_error` in the job row.
- **Proposal.** Typed exceptions in `core/errors.py` — `SourceMissing`, `ConversionFailed`,
  `GatewayUnavailable`, `InvalidOutput`, `WorkerError` — raised at the seams that know the cause
  (BackendClient 404 → `SourceMissing`; ffmpeg → `ConversionFailed`; OpenAI/httpx transport →
  `GatewayUnavailable`; §3.2 validation exhausted → `InvalidOutput`). The task wrapper maps type →
  reason code exhaustively; the old string matcher is deleted in the same increment (no users to
  protect — execution rule 3).
  Add `invalid_output` as a **new retry-reason code** (still retryable) so gateway-health vs
  model-output problems separate in observability. **Unchanged by design:** gateway-down stays
  retryable-then-durable (Celery bounded retry → backend `next_retry_at` → recovery beat), and
  fair-use **parking stays backend-owned** (`should_defer_dispatch` + recovery-beat resume) — the
  worker never learns about budgets.
- **Impact.** No cost/latency/quality change; correct dashboards and correct retry behavior on the
  edges the substrings misclassify.
- **Migration/eval.** Extends `tests/test_retry_reason.py`; backend accepts the new reason code
  (one-line enum/doc touch, backend-owned). Not an eval-relevant change (no prompt/model/output
  content), but the suite runs anyway with the increment it ships in.

---

## 4. Treatment-overlay contract (mandatory integration)

[ux-epic-treatment-overlay.md §4](ux-epic-treatment-overlay.md) hands this plan five requirements.
Mechanics, with ownership:

1. **Stable treatment keys — recommendation (answers the epic's open question #1):
   deterministic, backend-computed, content-anchored keys — not an LLM-emitted opaque id.**
   `treatment_key = "t|" + norm(area) + "|" + norm(product) + "|" + first(sourceCaptureIds)`,
   where `norm` is **Unicode-general, not Persian-specific** (revised in review): NFKC normalization
   + Unicode casefold + Unicode-wide digit folding + whitespace collapse. This treats fa/ar, Turkish
   (dotted/dotless i via casefold, ç/ş intact), and Latin text identically with no per-language
   tables — a Turkish clinic gets exactly the same key stability as a Persian one.
   Rationale: independent synthesis runs have no memory,
   so an LLM-emitted id can only be stable by *echoing* prior ids — which fails precisely on the
   hard case (a row splitting/merging); a content anchor is reproducible by construction, and it is
   the same pattern the safety overlay already proved. Two supports:
   - **Soft assist (synthesis contract change, this plan's side):** the payload already carries
     prior-visit and prior-draft treatments — include their keys and add an optional `priorKey` echo
     field to the output schema, instructing the model to repeat the key of a row it considers the
     same treatment. Used only as a **re-bind tie-breaker**, never authoritative.
   - **Deterministic re-bind pass (backend):** after each synthesis, per overlay entry: exact key
     match → bound; else a row sharing a source capture + normalized area (the split case, using
     `priorKey` as tie-breaker) → re-bind and surface the §3.3-epic reconcile; else the row is gone →
     the entry drops with it (matches the epic's source-de-effected edge case).
   - **Residual risk, accepted:** two same-area+product rows from one capture collide; disambiguate
     with an array-order ordinal suffix and let the reconcile signal surface any mis-bind. Recorded
     as a known limitation, revisited only if it bites in practice.
2. **Overlay application extended to treatments** (backend): add `treatment_overlay` to
   `OVERLAY_METADATA_KEYS` in `services/report_versions.py` (restore already excludes overlay keys —
   the invariant extends for free) and fold it at render. This plan specifies; backend implements.
3. **Reconcile signal on disagreement** (backend, deterministic — **no LLM**): on synthesis
   completion, diff fresh AI rows against overlay entries by key; a differing edited field ships
   both `aiValue` and the human `value` so the UI offers Keep/Use-AI. The model is never asked to
   reconcile human edits (ground-truth invariant: user state is applied after, and hidden from, AI).
4. **Projections read `report_version ⊕ overlay` — the lot-recall safety case** (backend): one fold
   function (`effective_treatments(session)`) becomes the *only* treatments read for recall,
   lot-recall cohorts, and smart lists. **Pipeline consequence this plan owns:** the patient-memory
   job input (`build_patient_memory_job_input` visit briefs) must also carry **overlaid** treatments,
   or the memory brief quotes a corrected-away lot/dose.
5. **Eval gate:** adding `treatmentKey`/`priorKey` to the synthesis output is a `session_organize`
   contract change → schema version bump (`…session-synthesis-output.v2`) + full `eval/run_all.py`
   with no extraction regression, plus a new `treatments_eval` case asserting key echo stability
   across an update run (golden-set addition → **consult the user first**, per CLAUDE.md §4).
6. **Language portability (new requirement from review — applies to ALL extracted structured data,
   not just treatments).** Problem: extracted display strings (treatment areas, safety-flag text,
   memory cards) are in the clinic's `reportLanguage`; if a clinic switches report language (fa→en)
   or a non-fa/en clinic onboards (Turkey), string-anchored keys fragment (the same cheek treatment
   dictated in fa then en yields two keys) and historical data has no recorded language to migrate
   from. Three measures, batched into the same schema-v2 bump:
   - **`lang` stamp on every extracted structured payload** (treatments, safety flags, memory
     cards, sections envelope): a BCP-47 field recording the language its display strings were
     generated in. Cheap now, impossible to reconstruct later — this is the reference-language
     field the review asked for.
   - **Canonical `areaCode` emitted by synthesis** alongside the display `area`: a closed,
     English-slug anatomic vocabulary (`cheeks`, `forehead`, `lips`, …) the prompt selects from.
     The treatment key then anchors on `areaCode|norm(product)` when present (products/brands are
     mostly Latin already), making keys **language-independent by construction** — a report-language
     switch or a Turkish clinic no longer breaks overlay re-binding or cross-visit projections.
     `norm(area)` remains the fallback for legacy rows.
   - **Migration story recorded, not built:** with `lang` + `areaCode` stamped, a future
     language-switch migration is a re-render of display strings (translate/re-extract per row,
     keys stable) — a batch job, not a schema crisis. Multi-language support itself stays out of
     scope; this requirement only guarantees it won't be a disaster later.

**Other UX epics checked for pipeline asks:**
[the attention model](../ux/states.md#attention-model) — severity (S1–S4) is an explicit backend **roll-up over
existing signals** (uncertainties, per-item confidence, safety flags, Q&A); no new synthesis fields
required. Optional, deferred: machine-readable uncertainty reason codes (today free strings) would
make the S2/S4 mapping less heuristic — a synthesis schema change, so if wanted it batches into the
same v2 bump as the treatment keys, eval-gated. Its "synthesis still in flight shows nothing" rule is
already served by `processing_status`. [tier-convergence](ux-epic-tier-convergence.md) — explicitly
adds **no** synthesis or structure to Basic; no gating change; it *depends on* the skip-sentinel +
deterministic-baseline seams this plan preserves. [unified-finder](../ux/screens/finder.md) (built) /
[session-layout-diet](ux-epic-session-layout-diet.md) — deterministic backend/frontend work, no
pipeline requirements.

---

## 5. Seam ownership vs the backend plan

| Change | AI-engine plan (this doc) owns | Backend plan / backend side owns |
|---|---|---|
| `processing.py` split, contracts, prompts | all of §2–§3 worker code | — |
| `services/ai_jobs/worker.py` (completion application) | — | backend plan increment 6 (its own eval-gated effort) — not bundled here |
| Treatment keys | key spec + `priorKey` schema/prompt change + memory-payload overlaid treatments | key computation, re-bind pass, overlay fold, reconcile diff, projections (`report_versions.py`, `sessions.py`, worker.py — narrow diffs, coordinated not batched) |
| Debounce + cache-hit-before-dispatch | invariants + QA criteria | config flip + `reports.py` dispatch guard |
| Retry taxonomy | typed exceptions + mapping | accept `invalid_output` reason code |
| Parking / fair-use | nothing (worker stays budget-blind) | as-is (`should_defer_dispatch`, recovery beat) |

## 6. Execution rules

1. **Eval gate (CLAUDE.md §4).** Every increment that moves or changes job code runs
   `apps/ai_engine/eval/run_all.py` where a gateway is reachable, with no scorecard regression. New
   golden-set cases (treatment-key echo, QA suite) are **consulted with the user first**.
2. **No silent behavior change.** Axis 1 is behavior-preserving; every behavior change is a named
   Axis-2/§4 increment. Typed-contract swaps ship with old-vs-new parity tests on malformed inputs.
3. **Compatibility posture (relaxed in review — no real users yet):** there are no production
   users or in-flight jobs to protect, so **no backward-compatibility gymnastics**: Celery task
   names stay stable as a *convenience* (renaming buys nothing), not a frozen contract — the
   Increment-0 snapshot test documents rather than forbids; the §3.6 legacy string-matcher fallback
   arm is deleted immediately (not kept "one release"); the schema-v2 bump needs no dual-read
   migration window; the `processing.py` re-export shim exists only for our own eval/test imports
   and can be deleted as soon as they're rewired.
4. **Fixture + gateway-less seams are frozen:** `TEST_CAPTURE_TEXT_BY_FILENAME`, deterministic
   fixture transcripts/captions, the synthesis skip sentinel, memory/QA `deterministicFallback`,
   blank-caption fallback. The e2e-stack suite is the proof and runs per increment.
5. **Vertical-agnostic rule holds:** prompt modules read `domain_framing`; no vertical vocabulary
   enters `prompts/` (extend `domain_descriptor` backend-side instead).
6. **The worker never imports backend code**; contracts stay worker-local (§2.2 decision).
7. **Close the loop:** doc updates named in the fold-destinations header land with the increment
   that makes them true; `python3 scripts/check-doc-links.py` before declaring any increment done.

## 7. Suggested overall order

1. Axis-1 increments 0–2 (net + `core/` + `jobs/` split) — unblocks everything, no behavior change.
2. §3.4.1 burst-coalescing dispatch (leading-edge + trailing) + §3.4.2 cache-hit-before-dispatch
   (backend-owned; biggest cost win, small diffs).
3. Axis-1 increment 3–4 (typed contracts + prompt versioning) → §3.6 retry taxonomy.
4. §3.2 structured-outputs rollout (per task) + §3.1 escalation tier.
5. §4 treatment-key contract (v2 schema bump, coordinated with the overlay epic's AES-1101).
6. Axis-1 increment 5 (delete shim, doc fold) — then fold + delete this plan.

---

## Adjacent epics spawned by the 2026-07-04 review

- [qa-knowledge-epic.md](qa-knowledge-epic.md) — implementing the Q&A jobs *correctly*: clinic QA
  library (template entry product feature) + retrieval-grounded drafting (RAG over approved past
  replies and templates). The `qa_draft`/`qa_revise` golden-set proposals moved there; this plan's
  Axis-1 move of the two jobs proceeds on unit tests, with evals riding the epic (decision 3 below).
- [ux-epic-report-history.md](ux-epic-report-history.md) — replace the bare "Undo last capture"
  button with a version-history surface over the existing `session_report_versions` store (navigate
  + preview + restore/pin). Pipeline-side it needs nothing new from this plan; it consumes the
  store + overlay fold as-is.

## Decisions from the 2026-07-04 review

1. **Treatment-key strategy — ACCEPTED** (content-anchored keys + `priorKey` tie-breaker + ordinal
   collision limitation), with the review amendments now in §4.1/§4.6: Unicode-general
   normalization and the language-portability requirement (lang stamps + canonical `areaCode`).
2. **Synthesis dispatch — RESOLVED (queue-collapse, user's design):** no timer/debounce at all.
   Single-flight per session + at most one pending job; queued jobs collapse by supersession (a
   pending job reads the full current capture set, so it absorbs later captures for free). First
   capture always synthesizes immediately. Companions: prompt-cache stable-prefix layout (~10×
   cheaper re-fed input) and a future internal per-clinic cost dashboard over the existing metering
   — observe real costs, optimize only if they prove to be a problem. §3.4.1 has the full design.
3. **QA evals vs the move — MOVE FIRST:** move `qa_draft`/`qa_revise` in the package split on unit
   tests now; their eval suite is scheduled with [qa-knowledge-epic.md](qa-knowledge-epic.md)
   (the golden set must cover retrieval-grounded drafting anyway).
4. **Schema v2 batching — ONE BUMP:** treatment keys + `priorKey` + machine-readable uncertainty
   codes + `lang` stamps + `areaCode` land in a single `session-synthesis-output.v2` (plus the
   other jobs' envelopes gaining `lang` in the same increment), one eval-gated migration.
5. **Structured outputs — ALL JOBS:** every JSON-emitting job uses gateway-enforced
   `json_schema` (gateway supports OpenAI + Gemini models OpenAI-style — confirmed), preceded by
   the per-model-family conformance test (§3.2). Transcription included, rolled out last.
6. **Streaming — REJECTED**, confirmed. Revisit only on real post-coalescing latency complaints.
