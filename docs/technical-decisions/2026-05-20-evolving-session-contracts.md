# Continuously Evolving Session Contracts (2026-05-20)

Sessions are created as `draft` when the first capture reaches the backend, but the explicit save action is no longer the boundary for reviewability. A session can receive captures, be reviewed, and be edited across all states; completion is auto-derived (see [Intelligence-Layer Simplification](2026-06-07-intelligence-layer-simplification.md)).

Every backend session payload exposes stable frontend contracts for `report`, `summaries`, `findings`, and `processingStatus`. The contract shapes were designed so the real AI pipeline could replace the early mocked writer without changing frontend object shape — which is what happened; the real pipeline now fills them.

The backend still owns report template selection and can pass template content to the AI engine through the report refresh endpoint. Patient full name and national ID remain special extracted metadata fields because they anchor patient matching.
