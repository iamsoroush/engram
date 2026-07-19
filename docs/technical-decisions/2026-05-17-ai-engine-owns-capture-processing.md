# AI Engine Owns Capture Processing Execution (2026-05-17)

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based placeholder completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns execution of the capture processing jobs (initially deterministic placeholders, since replaced by the real gateway-backed pipeline — see [ai_engine/processing.md](../ai_engine/processing.md)). The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.
