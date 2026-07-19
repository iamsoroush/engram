# AI-Engine Pipeline Hardening — Contracts, Prompts, Structured Outputs, Escalation (2026-07-04)

The AI-engine refactor (Axis-1 increments 3–4 + Axis-2 §3.1/§3.2/§3.6) hardened the worker without
changing any AI job's intended outputs. Decisions:

- **Typed contracts stay worker-local.** Each job's output shaping moved from ad-hoc dicts to pydantic
  models under `ai_engine/contracts/`, one per payload family, each owning an `OUTPUT_VERSION`. The
  backend keeps validating its own side over JSON-HTTP; a shared contracts package would couple the two
  deployables the boundary keeps apart. A model must never silently tighten the old tolerance —
  enforced by old-vs-new parity tests on malformed inputs.
- **Prompt provenance is recorded, never keyed on.** Prompts moved to versioned `ai_engine/prompts/`
  modules (`PROMPT_VERSION` + `build`); every envelope stamps `schemaVersion` + `promptVersion`. A
  hash-pin test forbids silent wording changes. Per pipeline-versioning **D1**, cache keys still ignore
  prompt version.
- **Structured outputs on all JSON-emitting jobs.** `response_format=json_schema` on every JSON task
  (the gateway enforces it OpenAI-style for OpenAI + Gemini), with one validation-failure retry
  appending the error before today's fallback. Behind the `AI_ENGINE_STRUCTURED_OUTPUTS_ENABLED`
  kill-switch; the typed contract remains the validation layer (defense in depth). Streaming stays
  **rejected**.
- **Retry taxonomy is type-based.** Typed exceptions (`core/errors.py`) raised at the seam that knows
  the cause replace the substring matcher; new retryable reason code **`invalid_output`** separates
  model-output failures from gateway outages. Gateway-down stays retryable-then-durable; fair-use
  parking stays backend-owned.
- **Escalation tier is worker-side + config-driven.** Optional `{…, escalation:{model?, reasoningEffort?}}`
  per task, fired on the validation-failure retry (and on a backend `escalate: true` correction hint —
  the hint's *emission* is backend-owned and deferred to the overlay/Wave-3 work). No speculative
  cheap-first escalation.

Eval golden-sets are unaffected (behavior-preserving); the `processing.py` re-export shim is retained
for eval/test imports. See [ai_engine/processing.md](../ai_engine/processing.md) and
[ai_engine/README.md](../ai_engine/README.md).
