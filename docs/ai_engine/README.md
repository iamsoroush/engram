# AI Engine Docs

AI engine docs describe the Celery worker boundary, the AI processing jobs, job retry/recovery
behavior, and the eval suite that gates changes to them.

## Documents

- [Processing](processing.md): the as-built AI jobs — audio transcription (+ patient information +
  intents), Pro photo captions with pairing/OOC attributes, note passthrough, the Pro report
  synthesis + treatment extraction job (deterministic baseline → synthesis overwrite, the A↔B
  contract, aftercare selections, safety flags + cross-visit reconcile), patient memory, the Q&A
  draft/voice-edit jobs, live per-task model config, retry/recovery, and the patient-matching
  boundary. Apply semantics live in [intelligence-layer.md](../intelligence-layer.md).
- [Evals](evals.md): the golden-set eval suite (`eval/run_all.py`) — two-tier scoring
  (deterministic safety gates + LLM judge), the fixture store and clinician recording workflow, the
  feedback→golden-set harvest loop, current coverage, and the CI reality. AI-job changes are gated
  on this scorecard (CLAUDE.md §4).

## Boundary

The backend owns API contracts, database schema, tenant scoping, and job rows. The AI engine
consumes named Celery tasks and reports lifecycle state through protected backend internal
endpoints. Processors are pure functions of their backend-built payloads — new AI jobs slot in
behind the same boundary without moving backend ownership into the worker.

## Package layout

The worker package (`ai_engine/`) is split by concern:

- `core/` — shared infrastructure: `gateway` (metered OpenAI-compatible client + model/effort/escalation
  resolution), `backend_client`, `media`, `text`, `domain` (the vertical-agnostic seam), `fixtures`,
  `errors` (typed exceptions → retry-reason codes), `structured` (schema-enforced calls + validation retry).
- `contracts/` — typed pydantic output models, one module per payload family, each owning its
  `OUTPUT_VERSION` and the tolerant parse/coercion for that family + its gateway `json_schema`.
- `prompts/` — one versioned module per prompt (`PROMPT_VERSION` + `build(context)`); shared framing in
  `prompts/_shared`. A hash-pin test forbids silent wording changes.
- `jobs/` — one module per job; thin runners that compose `core` + `contracts` + `prompts`.
- `processing.py` — a transitional re-export shim kept alive for eval/test imports.

Every completed job envelope stamps `schemaVersion` (its contract `OUTPUT_VERSION`) and `promptVersion`
(its prompt's version) as provenance the backend/eval can key regressions on.

## Caution: AI jobs must be vertical-agnostic

The platform is multi-vertical (aesthetics, therapy, dermatology, …). **A job/processor must never
hardcode or assume a vertical** — no "aesthetics clinic", no Botox/filler (or therapy) vocabulary, no
procedure/clinical-domain assumptions baked into a prompt or processor.

- **The backend owns the vertical.** It resolves the tenant's vertical and passes a `domain`
  descriptor into each job's context/payload — `label` plus optional `vocabulary` / `captionFindings`
  hints (see `app/services/verticals.py:domain_descriptor`, fed in via `build_transcription_context`,
  `build_capture_enrichment_context`, and the patient-memory payload).
- **The worker reads it and falls back to neutral.** The `prompts/` builders call
  `domain_framing(context)` (re-exported through `prompts/_shared` from `core.domain`), which returns a
  neutral `"clinic"` label and no vocabulary when `domain` is absent — so a worker is correct for *any*
  vertical, including ones with no descriptor yet.
- **Vertical-specific wording is allowed only when it is OPTIONAL and data-driven** — i.e. read from
  the passed `domain` with a neutral default — never embedded in the worker. To add or change a
  vertical's framing/vocabulary, extend `domain_descriptor`, not the prompts.

This keeps one set of processors serving every vertical, and keeps a therapy (or future) tenant from
being silently told it is an aesthetics clinic.
