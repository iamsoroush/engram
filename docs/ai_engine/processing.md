# AI Processing — the AI jobs (as built)

## Summary

The AI engine (`apps/ai_engine`) is a Celery worker that runs Engram's AI jobs against an
OpenAI-compatible gateway. Every processor is a real, gateway-backed job; deterministic and fixture
fallbacks keep Basic-tier and gateway-less environments fully working (**zero AI, never broken** —
see [Gateway-less + fixture fallbacks](#gateway-less--fixture-fallbacks)).

The **backend owns dispatch**: which tenants get which jobs (capability gating), the synthesis
quiet-period debounce, and fair-use parking are backend concerns — see
[docs/backend/processing.md](../backend/processing.md) and
[docs/business/ai-usage-limits.md](../business/ai-usage-limits.md). This doc covers the **worker
side**: what each job does, its contracts, and its fallbacks. Every AI job is **eval-gated**
([evals.md](evals.md)).

## Boundary

The backend is the producer: it creates durable `ai_jobs` rows, builds each job's full context
payload, and sends named Celery tasks. The AI engine is the consumer: it runs those task names,
fetches its payload from `POST /internal/ai/jobs/{id}/start`, and reports lifecycle state through the
protected backend internal endpoints (`/internal/ai/jobs/...`, authenticated with
`AI_ENGINE_INTERNAL_TOKEN`). The worker never imports backend code or touches the database — it is a
**pure function of its payload**, which is what keeps it vertical-agnostic and tier-unaware (the
backend attaches or withholds context; the worker just reads it).

## Job set

| Celery task | Scope | Does |
| --- | --- | --- |
| `ai_engine.process_audio_capture` | capture | Transcription + structured `patient_information` + `intents` |
| `ai_engine.process_image_capture` | capture | Pro photo caption + OOC/pairing attributes (+ downscale) |
| `ai_engine.process_text_capture` | capture | Pure passthrough — zero AI |
| `ai_engine.process_session` | session | Pro report synthesis + treatment extraction (`session_organize`) |
| `ai_engine.process_patient_memory` | patient | Combined summary + history + line-up card |
| `ai_engine.process_qa_draft` | patient | Pro Q&A reply draft (AES-402) |
| `ai_engine.process_qa_revise` | patient | Pro Q&A voice edit — revise/replace a draft |
| `ai_engine.recover_pending_ai_jobs` | beat | Periodic durable-job recovery ping |

`ai_jobs.job_type` values: `audio_capture_process`, `text_capture_process`,
`image_capture_process`, `capture_process` (legacy), `session_organize`, `patient_memory`,
`qa_draft`, `qa_revise`. Job rows carry tenant/capture/session/patient scope, lifecycle status
(`queued` → `running` → `succeeded`/`failed`), the durable retry schedule
(`attempt_count`, `last_attempted_at`, `last_dispatched_at`, `next_retry_at`, `last_error`,
`retry_reason`), and `output` JSONB. Every generated output embeds
`{"generated_by": "ai-engine", "ai_job_id": …, "generated_at": …}` so generated content stays
distinguishable from human-verified state.

## Per-capture jobs

On capture upload (for tenants whose capability set includes capture AI), the backend creates a
queued job row, marks the capture `processing`, and dispatches after the source object is durable.
Manual re-enqueue: `POST /api/v1/captures/{capture_id}/retry-processing`.

### Audio — transcription + patient information + intents

- Downloads the source through the internal API, converts to mono 16 kHz FLAC (`ffmpeg`), and sends
  it as `input_audio` to the configured gateway. No gateway → the job stays on the **retryable**
  path (`gateway_unavailable`); it never writes placeholder transcript text. The raw capture is
  durable regardless.
- Asks for strict structured JSON per the `2026-06-03.capture-intelligence.v1` schema
  ([intelligence-layer.md §4](../intelligence-layer.md)): `transcript` (required), `language`
  (`fa|en|mixed|unknown`), `clinical_summary`, `uncertainties`, `patient_information`, and
  `intents` (`assignment` with `basis: explicit|implicit`, `append`, `out_of_context`). Malformed
  structured output is a retryable worker failure; malformed *intents* are dropped field-by-field so
  a usable transcript is never lost (`normalize_intents`).
- The prompt is built from a tenant-scoped `transcriptionContext`: clinic assumptions, assigned
  patient, session metadata, previous same-session transcripts and notes, safe patient-history
  summary, the domain descriptor, and `preferredLanguage`. Transcription is verbatim in the spoken
  language and **original script — never translated or romanized** (a romanized Persian transcript
  breaks name matching).
- `detected_patient` remains as a compatibility projection of structured `patient_information`.

### Photo — Pro caption + enrichment attributes

- The Pro gate is the presence of `enrichmentContext` on the payload — the backend attaches it only
  when the tenant has the `image_caption` capability. Enriched photos are **downscaled
  worker-side** before sending (Pillow, longest edge 1280 px, JPEG q80, `detail: low`) since vision
  cost/latency scale with pixels.
- The caption is a **neutral image→text extractor**: an objective description of what is visibly
  present, in the source language/native script — never a diagnosis, severity, or "no signs of …".
- Alongside the free-text caption the model emits optional structured attributes:
  `intents.out_of_context` (`present/reason/confidence`, reusing the OOC apply path) and `pairing`
  (`region`, `laterality`, `view`, `phase`, `isProductLabel`). Before/after pairing itself is a
  deterministic backend step over these attributes, not an LLM job.
- `isProductLabel: true` triggers a **second high-detail pass** (longest edge 2048 px,
  `detail: high`) so lot/brand text on a product box stays legible — the lot feeds `treatments[]`
  and recall.
- **Basic / no gateway / empty gateway response:** the caption stays **blank** so the UI offers a
  manual "Add caption" instead of a meaningless placeholder. A gateway *error* propagates as a
  retryable failure. QA fixtures keep their deterministic caption.

### Note — pure passthrough

`process_text_capture` makes **no gateway call, ever** (note decoration was removed 2026-06-20;
report synthesis reads the raw note text directly). The job marks the note processed with its raw
text — preserving capture-chain ordering and `report_contribution` wiring — and the report reads the
raw `detail`.

## Session synthesis — report + treatments (`session_organize`)

The keystone Pro job: **one single-pass structured call** emits the per-visit report sections AND the
extracted `treatments[]` together (the A↔B contract), plus `aftercareSelections` and `safetyFlags`.

### Deterministic baseline → Pro synthesis overwrite

Once a session's capture chain drains, the backend **always** rebuilds the deterministic report first
(`regenerate_session_report`, synchronous, instant — Basic: one chronological section; the baseline
for Pro: grouped by-type sections), so a report is always present. Then, **iff** the tenant has the
`live_report_synthesis` capability, a gateway is configured, and an uncontributed reportable capture
exists, it dispatches `session_organize` (dispatch guards, debounce, and fair-use parking:
[docs/backend/processing.md](../backend/processing.md)). All settle triggers (capture add / edit /
delete / mark-relevant) re-synthesize over the full cumulative capture set.

The worker synthesizes only when the payload carries `reportSynthesis`; the result **overwrites** the
baseline (`report_model`, `session.summary`) and is final — the backend does not re-run the
deterministic regen over it. Not-Pro / no gateway / malformed or empty output → a **skip sentinel**
(`gateway_not_configured` / `empty_or_malformed_synthesis`): the deterministic baseline stands and
`treatments[]` stays empty. Basic never dispatches. A session is "complete" either way.

### Context

The session-processing input (versioned `2026-05-21.session-processing-input.v1`, extended for
synthesis) carries: `rawReportTemplate`, clinic, `assignedPatient` (DB assignment only),
`patientSummarizedHistory`, processed captures (`audio→transcript`, `photo→caption+pairing`,
`text→rawText` — text-only; OOC captures excluded), session metadata, `reportLanguage`, the domain
descriptor, the **prior `report_model` + a changeset** (capture ids added/removed/edited since the
last synthesis, enabling a stable targeted update), bounded **prior-visit `treatments[]`** (for
"same as last time"), the clinic's `aftercareTemplates`, and the patient's existing
`patientSafetyFlags`.

### Output — the A↔B contract

Schema `2026-06-15.session-synthesis-output.v1` (extends `2026-05-21.session-processing-output.v1`):

```jsonc
{
  "schemaVersion": "2026-06-15.session-synthesis-output.v1",
  "summary": "string",                 // 1–2 line visit summary → session.summary
  "language": "fa|en|mixed",
  "sections": [ ... ],                 // FIXED ids + order, rendered by the backend:
                                       // visit-summary, concern-goals, assessment,
                                       // treatment-performed, media, plan-followup, aftercare
                                       // blocks: {type:"paragraph",text} | {type:"image",captureId,caption}
  "treatments": [ /* TreatmentItem */ ],
  "aftercareSelections": [ { "templateId": "…", "status": "applies|conflicts|superseded", "note": "…|null" } ],
  "safetyFlags": [ { "kind": "allergy|contraindication|consent", "text": "…", "sourceCaptureIds": ["…"] } ],
  "sourceReferences": [ { "type": "capture", "captureId": "…" } ],
  "uncertainties": [ "string" ],       // drives review chips / Needs-input
  "generatedBy": "ai-engine", "generatedAt": "ISO-8601"
}

// TreatmentItem — stable queryable CORE + open attributes
{
  "area": "string", "product": "string", "brand": "string|null",
  "quantity": "number|null", "unit": "string|null",
  "quantityText": "string|null",        // VERBATIM, original script — display + audit
  "lot": "string|null",                 // dictated OR read from a product-label photo
  "confidence": 0.0, "sourceCaptureIds": ["…"], "evidence": "string|null",
  "carriedForward": false,              // "same as last time"
  "supersedesCaptureId": "string|null", // corrections (auditable/undoable)
  "attributes": { }                     // open map (needleGauge, depth, device, sessions, …)
}
```

Section titles localize to the report language (Persian titles when `reportLanguage=fa`); missing
sections are normalized to empty (`[]`) rather than padded. `product` is the generic category only
(ژل/فیلر، بوتاکس); `brand` is the commercial name verbatim — never merged.

### Extraction discipline (encoded in the prompt, asserted by evals)

- **Grounding:** work only from the captures + prior-visit context; invent nothing; leave a field
  `null` rather than guess. Prose follows `reportLanguage` in native script; brands, lots, quotes,
  and `quantityText` stay **verbatim in their original script** (never translated, romanized, or
  digit-normalized).
- **Update discipline:** captures are authoritative. Given the prior draft + changeset, keep
  unchanged prose byte-stable, recompute only affected sections/treatments, and remove anything no
  longer supported by a capture.
- **Corrections vs additions** (e.g. «ژل ۲ سی‌سی» then «ژل ۳ سی‌سی»): a correction (supersede) on an
  explicit cue («اشتباه گفتم», «منظورم…بود», "actually") or the same area+product+unit restated —
  emit one corrected item with `supersedesCaptureId`; an addition on additive cues («هم…هم»,
  «اضافه», "another") or a different area/product; **ambiguous → emit both + an uncertainty, never
  silently overwrite**. Deterministic post-processing of supersede/carry-forward is unit-tested
  backend-side.
- **Carry-forward:** only on an explicit "same as last time" cue → `carriedForward: true`, lower
  confidence, cite the prior visit. Never silently materialize a prior dose.
- **Aftercare selection** (intelligent, not keyword): judged by clinical relevance against the
  clinic's `aftercareTemplates` — one selection per protocol whose procedure was actually performed
  (completeness), compared per-procedure only. `applies` = fits; `conflicts` = the clinician
  dictated differing aftercare for that same procedure (the clinician's words win; the note names
  the difference); `superseded` = the clinician dictated their own full replacement.
- **Safety flags** (surface, never gate): one flag per distinct allergy / contraindication / consent
  statement a capture **explicitly** makes, quoted in the report language, never inferred and never
  a negative/absence statement. Errs toward inclusion — flags are auto-kept (opt-out): the clinician
  rejects a wrong one, and the backend persists the rest to the patient so they surface cross-visit.
- **Uncertainty → Needs-input:** every structured job emits `uncertainties[]` + per-item
  `confidence`; below a per-job threshold the backend raises a `needsReview` effect with a
  human-readable reason (ambiguous correction, missing-but-expected lot, low-confidence product,
  carried-forward dose, low-confidence caption/OOC), surfaced as capture chips + Needs-input items.

### Cross-visit safety reconcile (in-job second call)

When the visit's new `safetyFlags` plus the patient's existing flags total ≥ 2, the worker makes a
second, **selection-only** structured call (`reconcile_safety_flags`): keys + status out, never
text — dedup same-concept flags, keep distinct ones, supersede an explicit update (annotated, not
dropped), never merge across kinds, never drop a distinct allergy/contraindication. It is
best-effort and additive: any failure or malformed output falls back to the deterministic union (the
safety floor) without failing the synthesis. Decisions ship as
`extracted_metadata.safety_reconciliation`.

### Backend assembly

`treatments[]` → `session.extracted_metadata.treatments` (post-processed — validate / supersede /
carry-forward — then the queryable store behind recall, lot tracking, and smart lists: deterministic
queries, not LLM jobs). The `treatment-performed` section is re-rendered **from** `treatments[]` so
prose and store cannot diverge. `sections[]` → `report_model`; `summary` → `session.summary`; every
image-block `captureId` is validated against the session's captures and unknowns are dropped.

### Hard constraints (always true)

Single-pass structured LLM calls (no agents/tool loops) · direct-DB context injection (no vector
RAG) · one OpenAI-compatible gateway, per-task model + `reasoning_effort` via config · **no
temperature** (GPT-5-class models reject it; stability comes from structured output + low effort) ·
schema-enforced JSON for synthesis/extraction, free text + attributes for captions · Persian +
English in native script, **never romanize** · Basic and gateway-less environments run zero AI and
must never break · capture durability is sacred (enrichment lag is a quiet state, never an error).

## Patient memory (combined summary + history, Pro)

The patient-level **summary** (card) and **history** (timeline brief) are produced by a single
AI job, `patient_memory` (patient-scoped via `ai_jobs.patient_id`). One model call returns
both — shared context (≈half the input cost) and a card summary guaranteed consistent with the
history.

- **Incremental input.** The payload (`build_patient_memory_job_input`) carries the patient's
  *prior* memory plus compact per-visit briefs (each session's distilled summary + capture
  counts/types **+ that visit's `treatments[]`** from synthesis, so recall is grounded —
  "last visit: Voluma 0.3 mL, left cheek"), not raw transcripts — so cost stays ~flat as visits
  grow. It also includes a `deterministicFallback` (the backend's deterministic generator output).
- **Worker** (`completed_patient_memory_output`): when a gateway is configured it asks the model for
  strict JSON (`summary` + `history{snapshot, sections, visits}` + a compact `card{storySoFar,
  rightNow, flags}`) and validates it; if the gateway is absent or the response is unusable it
  returns the `deterministicFallback`, so the job always completes with valid memory. Output
  `source` is `ai:<model>` or `mock-deterministic`.
- **Decoupled from per-capture; refreshed when a human is about to look.** Memory is **not** rebuilt
  on capture/session completion (that would rebuild mid-visit, before treatments exist, and for
  patients nobody will see). `maybe_dispatch_patient_memory_job` is capability-gated
  (`cross_visit_synthesis`) + self-gating (no capture job in flight, dedup on an in-flight
  `patient_memory` job); the *triggers* are three priority classes (lower Celery/Redis
  `priority_steps` number is served first, so the more-imminently-viewed patient jumps the queue):
  - **1st class — patient OPENED + stale** (`priority` 0): the detail endpoint / line-up recap calls
    `maybe_refresh_stale_patient_memory` when memory is **stale** (`patient_memory_is_stale`: a visit
    changed since the last completed build), kicking the rebuild (`updating → ready`) at the moment a
    clinician is reading it.
  - **2nd class — patient ADDED TO THE LINE-UP + stale** (`priority` 3): `create_worklist_entry`
    fires the same refresh when staff queue a patient, so the brief is ready by the time the clinician
    taps through.
  - **3rd class — background quiescence sweep** (`priority` 6): `sweep_stale_patient_memory`, run on
    the EXISTING Celery-beat recovery loop (`/internal/ai/jobs/recover`), refreshes stale patients
    nobody touched whose latest visit has been idle ≥ `patient_memory_quiescence_seconds` (~30 min),
    newest-idle first, capped per beat.

  All three coalesce to ≤1 job per patient per window; capture/session jobs keep priority 0, so a
  memory backlog never delays interactive processing. See `READ_/LINEUP_/SWEEP_DISPATCH_PRIORITY`.
- **Completion** (`complete_patient_memory_worker_job` → `apply_patient_memory_output`) writes
  `patients.memory` (`status:"ready", summary, history, card, source, updated_at`); the read path
  serves the stored brief, and the detail endpoint layers the **line-up card** on top (see below).
- **Basic** never runs this job — its summary/history are deterministic, finalized lazily on read. A
  Pro read only finalizes deterministically as a safety net when nothing is in flight, so Pro memory
  is never permanently stuck in `updating` (even if a gateway-bound job died).

### Line-up card (Pro, worklist recap)

The patient-memory detail (`GET /patients/{id}/memory`) carries a compact, glanceable `lineupCard`
for the worklist recap. Its text (`storySoFar` ≤2 sentences, `rightNow` ≤2 sentences, `flags`) is the
AI job's `card` projection — persisted on the patient with a deterministic history-derived fallback,
so it is never blank. **`hero` and `sinceLastVisit` are computed deterministically (no LLM)** at read
time so they stay fresh against current captures: `hero` is the most recent clear *after*-photo of the
primary (most-photographed) area, else the latest photo (OOC + product-label shots excluded);
`sinceLastVisit` is a delta line grounded in the latest visit's `treatments[]`. `status` mirrors the
memory lifecycle so the card animates `updating → ready`. Basic tenants get no card.

## Q&A draft + voice edit (`qa_draft` / `qa_revise`, Pro)

The post-session patient Q&A jobs (AES-402; API contract:
[docs/backend/aes-pro-qa-api.md](../backend/aes-pro-qa-api.md)). Both are patient-scoped; the target
thread/message rides in `AiJob.result_metadata`. Everything is a **suggestion** — the doctor reviews
and approves before anything reaches the patient.

- **`qa_draft`** drafts a warm, clinically-cautious reply to a patient's between-visits question,
  grounded in the doctor's prior answers + this patient's context (`qaDraft` payload), inventing no
  clinical facts and escalating to the clinic when warranted.
- **`qa_revise`** takes the doctor's spoken voice note (downloaded and sent as `input_audio`
  alongside the current draft), classifies it as a **revision** of the draft or an **entirely new
  reply** (strict JSON `{mode: revise|replace, reply}`), and produces the final text.
- Both fall back to the backend-provided `deterministicFallback` when no gateway is configured or
  the output is unusable, so the job always completes and the inbox always has a suggestion. Model
  resolution uses the `qa_draft` task label (falls back to the transcription gateway).
- **Known gap:** these are the only AI jobs **without an eval suite** — see
  [evals.md](evals.md#coverage-gaps).

## Per-task models (live-selectable)

Each AI task label — `transcription`, `caption`, `report_synthesis`, `patient_memory`, `qa_draft` —
can run on its own model (notes are a pure passthrough: no AI, no model). The model id is
**live-configurable at runtime, globally**: the backend stores a per-task override in the
`app_config` table (key `ai_models`), editable via `GET`/`PUT /api/v1/ai-config/models` (an
API-only knob — no user-facing picker), and surfaced to the worker in every job payload as `aiModels`. The
worker resolves: payload `aiModels[task]` → env `AI_ENGINE_<TASK>_MODEL` → env
`AI_ENGINE_TRANSCRIPTION_MODEL` (`resolve_model` / `gateway_settings_for`). A task entry may be a
bare model string or `{model, reasoningEffort}` — reasoning effort is the quality/stability knob for
structured synthesis (`resolve_reasoning_effort`; there is **no temperature**). Because the backend
reads the override when it builds the payload at job start, a change takes effect on the **next
request** with no restart. Gateway URL/key stay in env only (`AI_ENGINE_<TASK>_BASE_URL` /
`_API_KEY`, blank → the shared `transcription_*` gateway); secrets are never stored in the DB.

## Vertical-agnostic prompts (all jobs)

No processor hardcodes a vertical. The backend resolves the tenant's vertical to a `domain`
descriptor (`label` + optional `vocabulary` / `captionFindings` —
`app/services/verticals.py:domain_descriptor`) and includes it in each job's context/payload. Each
prompt builder reads it via `processing.domain_framing()`, which falls back to a neutral `"clinic"`
with no vocabulary when the descriptor is absent — so the same worker serves aesthetics, therapy, and
future verticals. Add a vertical's wording by extending `domain_descriptor`, never by editing the
prompts. See the [README caution](README.md#caution-ai-jobs-must-be-vertical-agnostic).

## Retry + recovery

If a worker attempt raises, the task logs the exception, stores the last error + retry reason on the
job row, and lets Celery perform its bounded local retry; the backend also stores `next_retry_at` with
bounded backoff. After Celery retries are exhausted, retryable jobs remain durable `failed` rows.

The reason is **type-based** (`ai_engine/core/errors.py`): each failure is raised at the seam that
knows the cause as a typed `WorkerError` subclass — `SourceMissing` (`source_missing`; backend file
404 / missing content), `ConversionFailed` (`conversion_failed`; ffmpeg), `GatewayUnavailable`
(`gateway_unavailable`; gateway transport / not configured), `InvalidOutput` (`invalid_output`; model
returned malformed/unusable output — separates model failures from gateway outages), else
`worker_error`. `retry_reason_for_exception` maps type → code exhaustively (no substring matching).

AI jobs are durable backend rows: queued jobs, retryable failed jobs whose `next_retry_at` has
arrived, and stale running jobs are re-dispatched after broker or worker downtime. Recovery runs
three ways — staff/admin can call `POST /api/v1/ai-jobs/recover`, a worker calls the internal
recovery endpoint on startup, and the worker's Celery-beat loop pings it periodically — so delayed
work resumes without user action. Jobs with `result_metadata.retryable=false` are terminal
(manual-attention) and skipped; backend target checks mark jobs for deleted captures/sessions
non-retryable so they never retry forever. Capture rows stay `processing` through retryable
failures, so the UX shows a calm generic processing state (AI-out is silent and self-healing).

Job rows are visible via `GET /api/v1/ai-jobs/{job_id}` and
`GET /api/v1/sessions/{session_id}/ai-jobs`; workers post partial output through
`POST /internal/ai/jobs/{job_id}/progress`.

## Gateway-less + fixture fallbacks

Every job completes sensibly with no gateway, so Basic tenants, dev stacks, and CI never break:

- **Audio:** retryable (waits for a gateway) — except QA fixtures, which get their deterministic
  transcript.
- **Photo:** blank caption (manual add); fixtures keep their deterministic caption.
- **Note:** passthrough always (no gateway involved).
- **Synthesis:** skip sentinel → the deterministic baseline report stands, `treatments[]` empty.
- **Patient memory / Q&A:** the payload's `deterministicFallback` is returned, so the job always
  completes with valid output (`source: "mock-deterministic"`).

The deterministic QA fixtures under `test_data/` are recognized by filename/content
(`TEST_CAPTURE_TEXT_BY_FILENAME` in `core/fixtures.py`); uploading them produces predictable
transcripts, captions, report sections, and rendered markdown so ingestion → processing → report
rendering can be tested end to end without AI.

## AI patient matching (backend-owned, worker-fed)

Patient matching is backend-owned and reviewable; the worker's contribution is the structured
`patient_information` + `intents.assignment` from transcription. The backend preserves
`Patient.display_name` exactly as staff entered it and stores deterministic search aliases in
`patient_identifiers` (national ID digits-only, `+98` phone normalization, lowercased email,
Persian/Arabic character + digit normalization, rough Persian↔Latin aliases).

Matching runs the ladder, in order:

1. exact national ID
2. exact phone or email
3. exact normalized alias
4. fuzzy alias candidate search (token-aware: a first-name-only mention still surfaces the
   full-named patient as a `possible_match`)
5. optional LLM ranking, only over the small backend-selected candidate set

The LLM step is ranking-only: it must not search all patients, create patients, assign sessions,
merge patients, or rewrite display names.

**Provenance:** matching output is stored as `patient_match_candidate` on capture metadata (and
mirrored into session extracted metadata for unassigned sessions). Deterministic `matched` results
assign with `ai_patient_action` provenance; deterministic `no_match` with usable extracted identity
creates an AI-origin patient (flagged for staff verification) and assigns it. Every AI or staff
action is appended to `patient_assignment_timeline`; the latest valid event becomes
`active_patient_assignment_action`, and events whose capture was deleted are skipped on recompute —
which is what makes assignment undo capture-shaped. *When* an extracted identity may apply, override,
or only suggest (first-identity-wins, explicit-basis override, implicit → suggestion, match
strictness) is the apply-semantics contract in
[intelligence-layer.md §5](../intelligence-layer.md).

## AI-usage metering

Every gateway call's `usage` block is captured per job (a metered client wraps the OpenAI client;
transcription also records audio seconds, priced per-minute) and shipped to the backend with the
completion callback — real spend, not estimates. Budgeting, caps, and enforcement:
[docs/business/ai-usage-limits.md](../business/ai-usage-limits.md).
