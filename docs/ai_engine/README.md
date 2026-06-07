# AI Engine Docs

AI engine docs describe the Celery worker boundary, placeholder processors, job recovery behavior, and future replacement path for real AI processors.

## Documents

- [Processing](processing.md): the AI engine's capture/session processors — real transcription,
  Pro enrichment (captions/decoration), deterministic report generation, durable retry, and the
  patient-identity/matching boundary (the now-implemented durable-retry + context-rich transcription
  + patient-extraction direction lives here and in [intelligence-layer.md](../intelligence-layer.md)).

## Direction

The backend owns API contracts, database schema, tenant scoping, and job rows. The AI engine consumes named Celery tasks and reports lifecycle state through protected backend internal endpoints. Real AI processors should replace placeholder job bodies without moving backend ownership into the worker.
