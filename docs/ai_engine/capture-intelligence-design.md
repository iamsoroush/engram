# Pro capture-intelligence — build design

> **Status:** approved Phase-1 design (product-owner review). Authoritative spec for the Pro
> capture-intelligence wave. Aesthetics-first but **vertical-agnostic** via the domain descriptor.
> Companion: [intelligence-layer.md](../intelligence-layer.md), [processing.md](processing.md),
> [redesign-foundation §3](../ux/redesign-foundation.md).

## Confirmed decisions (this wave)

- **Build keystone-first.** Job 3 (report synthesis + treatment extraction) is built end-to-end FIRST
  — it locks the A↔B contract everything else consumes and is the riskiest piece — then Jobs 2/4,
  removals, and frontend fan out. They share `processing.py`/`worker.py`/`reports.py`, so parallel-first
  would collide.
- **Treatment-extraction accuracy gate = a minimal Farsi golden set** (~12 real dictation cases:
  corrections, additions, carry-forward, lot-on-label) asserted against expected `treatments[]`, run
  against the gateway — the gate before dose extraction is trusted clinically. (Full eval harness across
  all jobs stays deferred.) Plus deterministic CI unit tests for the correction/carry-forward/supersede
  post-processing logic.
- **Decouple Story A's config plumbing from its super-admin gate.** Per-task `{model, reasoningEffort}`
  config ships *with* the synthesis (it's the quality knob); the platform-admin role is a separate story.
- **Synthesis model is a knob to measure.** Start `gpt5.4-nano` low-effort; measure quality on the
  golden set and be ready to bump that one task's model/effort via config.

## Hard constraints

Single-pass structured LLM calls (no agents/tool loops) · direct-DB context injection (no vector RAG) ·
existing OpenAI-compatible gateway, per-task model + reasoning_effort via config · **no temperature**
(GPT-5-class rejects it; stability from structured output + low effort) · schema-enforced JSON for
synthesis/extraction, free text + attrs for captions · Persian + English, native script, **never
romanize** · graceful deterministic fallback — **Basic and gateway-less envs run zero AI and must never
break** · capture durability is sacred (enrichment lag is a quiet state, never an error).

## Job set (final — note-decoration removed)

1. **Transcription** (audio) — exists; minor hardening. `gemini-3.1-flash-lite`, low effort, structured.
   No gateway → retryable (`gateway_unavailable`); raw capture durable regardless.
2. **Image caption** (photo, Pro) — exists; extend. Free-text caption **+ optional attributes**:
   out-of-context `{present,reason,confidence}` (reuses the OOC path); pairing `{region, laterality,
   view, phase, isProductLabel}` (pairing is a **deterministic backend step** over these, not an LLM
   job). **Worker-side downscale before send** (Pillow, longest edge ~1024–1536px, JPEG q80, detail:low;
   product-label shots use detail:high for legible lot/brand). No gateway/Basic → blank caption (manual add).
3. **Report synthesis + treatment extraction** (session-level, Pro) — **NEW (revives `session_organize`).
   The centerpiece.** One single-pass structured call emits the report sections AND `treatments[]`
   together. See below.
4. **Patient memory** (patient-level, Pro) — exists; **decouple from per-capture** → read-triggered
   (patient page/line-up opens + stale) + quiescence sweep (~30 min idle, via the existing Celery-beat
   loop); coalesce ≤1/patient/window. Briefs include each visit's `treatments[]`. Adds a glanceable
   **line-up card** (≤2 short paragraphs, deterministic `heroCaptureId`, "since last visit" delta, flags).

## Job 3 — synthesis + extraction (the keystone)

- **Trigger:** at chain-drain. The **deterministic baseline always runs first** (`regenerate_session_report`,
  instant) so a report is always present. Then **iff** `tenant_has_capability(LIVE_REPORT_SYNTHESIS)` +
  gateway configured + an uncontributed reportable capture → dispatch `session_organize`. All settle
  triggers (add/edit/delete/mark-relevant) re-synthesize over the full cumulative set, debounced via the
  existing `session_has_active_report_job` + `session_has_uncontributed_capture` guards.
- **Context** (extend `build_session_processing_input`): `rawReportTemplate`, clinic, `assignedPatient`,
  `patientSummarizedHistory`, captures `{audio→transcript, photo→caption+pairing, text→rawText}`, session
  meta — **plus** `reportLanguage` + domain descriptor, the **prior `report_model` + a changeset** (ids
  added/removed/edited since last synthesis → stable targeted update), and **bounded prior-visit
  `treatments[]`** (`referencePriorVisit`, for "same as last time"). Text-only (reads enriched texts, not
  raw images); OOC captures already excluded.
- **Prompt:** ONE structured per-visit report + extracted performed treatments; strict JSON; setting =
  `{domain.label}` (neutral "clinic" when absent); populate the fixed section ids; ground every statement
  in captures (invent nothing); prose in `{reportLanguage || template default}` native script even when
  captures differ, but keep **verbatim** quantities/brands/`quantityText`; leave null rather than guess.
  - **Update discipline:** captures are authoritative; update the prior draft to match; remove unsupported;
    keep unchanged prose byte-stable; recompute only affected sections/treatments.
  - **Carry-forward:** only on explicit "same as last time" → `carriedForward:true` + lower confidence +
    cite prior visit (→ confirm). Never silently materialize a prior dose.
  - **Corrections vs additions** (e.g. `ژل ۲ سی‌سی` then `ژل ۳ سی‌سی`): correction (supersede) on a cue
    (`اشتباه گفتم`, `منظورم…بود`, "actually", "make that") or same area+product+unit restated; addition on
    additive cues (`هم…هم`, `اضافه`, "another") or different area; **ambiguous → flag for confirmation, never
    silently overwrite**; record `supersedesCaptureId` (auditable/undoable).
- **Output:** `2026-06-15.session-synthesis-output.v1` (extends `2026-05-21.session-processing-output.v1`).
  Model `gpt5.4-nano` low `reasoning_effort`, structured output, **no temperature**.
- **Fallback (never breaks):** not Pro / no gateway / malformed / repeated failure → the deterministic
  grouped report (already the baseline) stands, `treatments[]` empty. Basic never dispatches. Malformed →
  retryable; terminal failure → session still "complete" with the deterministic report.

## A↔B contract (synthesis output)

```jsonc
{
  "schemaVersion": "2026-06-15.session-synthesis-output.v1",
  "summary": "string",                 // 1–2 line visit summary -> session.summary
  "language": "fa|en|mixed",
  "sections": [                        // FIXED ids + order; rendered by the backend
    { "id": "visit-summary",       "title": "...", "blocks": [ { "type": "paragraph", "text": "..." } ] },
    { "id": "concern-goals",       "title": "...", "blocks": [ ... ] },
    { "id": "assessment",          "title": "...", "blocks": [ ... ] },
    { "id": "treatment-performed", "title": "...", "blocks": [ ... ] },  // PROSE MIRROR of treatments[]
    { "id": "media",               "title": "...", "blocks": [ { "type": "image", "captureId": "...", "caption": "..." } ] },
    { "id": "plan-followup",       "title": "...", "blocks": [ ... ] },
    { "id": "aftercare",           "title": "...", "blocks": [ ... ] }
  ],
  "treatments": [ /* TreatmentItem */ ],
  "sourceReferences": [ { "type": "capture", "captureId": "..." } ],
  "uncertainties": [ "string" ],       // drives review chips
  "generatedBy": "ai-engine",
  "generatedAt": "ISO-8601"
}

// TreatmentItem — stable queryable CORE + open attributes
{
  "area": "string", "product": "string", "brand": "string|null",
  "quantity": "number|null", "unit": "string|null",
  "quantityText": "string|null",        // VERBATIM, original script — display + audit
  "lot": "string|null",                 // dictated OR read from a product-label photo
  "confidence": 0.0, "sourceCaptureIds": ["..."], "evidence": "string|null",
  "carriedForward": false,              // "same as last time"
  "supersedesCaptureId": "string|null", // corrections (auditable/undoable)
  "attributes": { }                     // open map (needleGauge, depth, device, sessions, ...)
}
```

**Backend assembly:** `treatments[]` → `session.extracted_metadata.treatments` (the queryable store for
recall / lot tracking / smart lists — deterministic queries, not LLM jobs); `treatment-performed` blocks
rendered FROM `treatments[]` (prose + store can't diverge); `sections[]` → `report_model` via
`report_model_from_session_processing_output`; `summary` → `session.summary`. Photos: synthesis places
inline `{"type":"image","captureId":…}`; `render_report_body_markdown` resolves to the file endpoint.
**Validate every `captureId` against the session's captures and drop unknowns** (renderer currently trusts
model output — gap to close).

## Backend/worker seams (change list)

1. Revive `session_organize` dispatch at chain-drain for Pro+gateway, AFTER the deterministic baseline,
   debounced via existing guards (`orchestration.py`, `reports.py`).
2. **Remove/guard the trailing deterministic regen in `complete_session_worker_job`** on the synthesis
   path — the LLM write is final; don't clobber it.
3. New worker task `report_synthesis` in `processing.py` (prompt builder + `json_schema` structured output
   + parse/validate + deterministic fallback); register in `gateway_settings_for`/`resolve_model`.
4. Extend `build_session_processing_input` (domain, prior `report_model`, changeset, bounded prior-visit
   `treatments[]`; text → rawText).
5. New output version + `treatments[]` in `report_model_from_session_processing_output` +
   `complete_session_worker_job` → write `extracted_metadata.treatments`, render `treatment-performed`.
6. `captureId` validation in assembly / `render_report_body_markdown`.
7. Caption job: downscale + detail level; emit OOC + pairing attrs + `isProductLabel`; high-res lot path.
8. Per-task `{model, reasoningEffort}` threaded in `aiModels` + applied in the worker; **no temperature**.
9. Patient-memory triggers reworked (read-triggered + quiescence; drop per-capture); briefs include
   treatments; line-up card + `heroCaptureId`.
10. Uncertainty → Needs-input contract (below).
11. Doc updates: `intelligence-layer.md` §3 + `processing.md` → "deterministic baseline; Pro+gateway
    overwrites with single-pass LLM synthesis."

## Removals — note decoration

Synthesis reads raw note text, so decoration is redundant. Keep `text_capture_process` as a pure
passthrough (marks the note processed with raw text — preserves chain ordering + `report_contribution`)
but no gateway call. Drop `decorated_text` everywhere (backend metadata, `decoratedText` in the input,
the preference in `_capture_report_text`, `textNotes` in `build_transcription_context` → use raw `detail`);
remove the `note_decoration` task/env. Frontend: note card shows raw text; inline-edit edits the raw note.
**Captions are not removed.**

## Cross-cutting — uncertainty → Needs-input

Uniform "AI unsure → tell the human", reusing the existing effect/Needs-input surface. Every structured
job emits `uncertainties[]` + per-item `confidence`; below a per-job threshold the backend raises a
`needsReview` effect with a human-readable reason. Applies to: patient matching (already), treatment
extraction (ambiguous correction, missing-but-expected lot, low-confidence product, carried-forward),
captions (low confidence / OOC). Surfaces as the existing capture chips + Needs-input items.

## Sequencing

`capture → per-capture jobs (audio→transcription, photo→caption, note→raw text, no AI) → chain drains →
deterministic baseline (ALWAYS) → [Basic/no-gateway: done] / [Pro+gateway+uncontributed: session_organize
(gpt5.4-nano, 1×/settle) → overwrite report_model + store treatments[] + mark complete; DO NOT re-run the
deterministic regen] → patient memory refreshed read-triggered/quiescence (not per capture)`.

## Handoff stories (separate build items)

- **Story A** — lock AI-model config to a platform super-admin + add thinking level. No platform role
  exists today (roles are tenant-scoped); introduce a platform gate, remove the picker from tenant
  Settings, extend config to `{model, reasoningEffort}`. *(Config plumbing ships with the keystone; the
  super-admin gate is this story.)*
- **Story B** — per-session "Share with patient" (reuses `PatientShare.session_id` + `create_patient_share`):
  share the same synthesized report (curated media + aftercare), scoped to the session.
- **Story C** — polished report rendering (**needs a UX step**): a good-looking rendering of the one
  synthesized report, clinical + shareable (before/after slider, clean sections, aftercare).
  *UX step delivered (design, for review):* [redesign-pro-report.md](../ux/redesign-pro-report.md)
  + prototype [`aesthetics-pro-report.html`](../../apps/frontend/design-prototypes/aesthetics-pro-report.html).

## Out of scope / always true

Deferred: full evaluation/golden-set harness (a *minimal* extraction golden set is in-scope, above).
One report (no separate patient projection — share the same report). Always: Basic + gateway-less = zero
AI, never break; all prompts vertical-agnostic via the domain descriptor; capture durability sacred.
