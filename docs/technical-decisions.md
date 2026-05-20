# Technical Decisions

## UX Docs Are The Current User-Facing Behavior Map

The compact docs under `docs/ux/` describe the currently implemented user-facing behavior. Future changes that alter screens, navigation, visible states, or workflows should update the relevant UX docs without duplicating backend API schemas.

## AI Engine Owns Capture Processing Execution

Capture upload persists the source object, capture row, and queued processing job before dispatching Celery. The backend no longer derives time-based placeholder completion during reads.

The backend is the producer and sends named Celery tasks. `apps/ai_engine` is the worker app and owns deterministic placeholders for audio, text, and image capture processing. The AI engine uses backend internal HTTP endpoints for start/complete/retry/fail updates instead of importing backend modules or writing directly to Postgres.

## Continuously Evolving Session Contracts

Sessions are created as `draft` when the first capture reaches the backend, but the explicit save action is no longer the boundary for reviewability. A session can receive captures, be reviewed, be edited, and be verified across all states.

Every backend session payload exposes stable frontend contracts for `report`, `summaries`, `findings`, and `processingStatus`. Phase 2.1 writes deterministic mocked outputs into those contracts so the real AI pipeline can later replace the mock writer without changing frontend object shape.

The backend still owns report template selection and can pass template content to the AI engine through the report refresh endpoint. Patient full name and national ID remain special extracted metadata fields because they support deterministic placeholder matching now and future patient matching later.
