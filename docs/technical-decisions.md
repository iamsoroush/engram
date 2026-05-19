# Technical Decisions

## UX Docs Are The Current User-Facing Behavior Map

The compact docs under `docs/ux/` describe the currently implemented user-facing behavior. Future changes that alter screens, navigation, visible states, or workflows should update the relevant UX docs without duplicating backend API schemas.

## AI Engine Owns Capture Processing Execution

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based placeholder completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns deterministic placeholders for audio, text, and image capture processing. The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.

## Draft Sessions And Session Reports

Sessions are created as `draft` when the first capture reaches the backend. The explicit save action is the boundary that queues session-level processing and report generation.

The backend owns report template selection and passes template content to the AI engine. The initial default template is markdown; future custom templates can reuse the same job contract.

Patient full name and national ID are special extracted metadata fields. The backend stores patient national IDs as patient identifiers so generated session metadata can be matched against existing patients.
