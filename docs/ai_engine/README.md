# AI Engine Docs

AI engine docs describe the Celery worker boundary, placeholder processors, job recovery behavior, and future replacement path for real AI processors.

## Documents

- [Processing](processing.md): the AI engine's capture/session processors — real transcription,
  Pro enrichment (captions/decoration), deterministic report generation, durable retry, and the
  patient-identity/matching boundary (the now-implemented durable-retry + context-rich transcription
  + patient-extraction direction lives here and in [intelligence-layer.md](../intelligence-layer.md)).

## Direction

The backend owns API contracts, database schema, tenant scoping, and job rows. The AI engine consumes named Celery tasks and reports lifecycle state through protected backend internal endpoints. Real AI processors should replace placeholder job bodies without moving backend ownership into the worker.

## Caution: AI jobs must be vertical-agnostic

The platform is multi-vertical (aesthetics, therapy, dermatology, …). **A job/processor must never
hardcode or assume a vertical** — no "aesthetics clinic", no Botox/filler (or therapy) vocabulary, no
procedure/clinical-domain assumptions baked into a prompt or processor.

- **The backend owns the vertical.** It resolves the tenant's vertical and passes a `domain`
  descriptor into each job's context/payload — `label` plus optional `vocabulary` / `captionFindings`
  hints (see `app/services/verticals.py:domain_descriptor`, fed in via `build_transcription_context`,
  `build_capture_enrichment_context`, and the patient-memory payload).
- **The worker reads it and falls back to neutral.** Prompt builders call
  `processing.domain_framing(context)`, which returns a neutral `"clinic"` label and no vocabulary
  when `domain` is absent — so a worker is correct for *any* vertical, including ones with no
  descriptor yet.
- **Vertical-specific wording is allowed only when it is OPTIONAL and data-driven** — i.e. read from
  the passed `domain` with a neutral default — never embedded in the worker. To add or change a
  vertical's framing/vocabulary, extend `domain_descriptor`, not the prompts.

This keeps one set of processors serving every vertical, and keeps a therapy (or future) tenant from
being silently told it is an aesthetics clinic.
