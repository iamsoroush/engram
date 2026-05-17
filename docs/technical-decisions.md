# Technical Decisions

## AI Engine Owns Capture Processing Execution

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based fake completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns deterministic placeholders for audio, text, and image capture processing. The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.
