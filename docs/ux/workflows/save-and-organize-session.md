# Save And Organize A Session

## User Goal

Turn a draft capture session into generated summary, metadata, and report output for assignment, review, and verification.

## Entry Point

- Capture screen `Save session` button on a synced draft/reopened/failed session.
- Session review `Save session` or failed-session `Retry` button for eligible sessions.

## Current Behavior

1. User captures one or more items.
2. Local sessions must finish syncing before they can be saved; the button reads `Syncing first`.
3. User selects `Save session`.
4. The frontend calls the backend save endpoint with the default report template key.
5. The session moves to `Processing`.
6. The frontend shows a processing toast and schedules a refresh.
7. When the session job succeeds, Organize places the session in `Needs review` when a patient is assigned, otherwise `Unassigned`.
8. Session review shows generated report, editable metadata, patient search/creation, and patient-information warnings when present.
9. If a user adds a capture after processing, the session returns to `Draft` and the previous generated output is labeled stale until processing runs again.

## System Behavior

- Backend rejects save attempts for sessions without captures or sessions not ready to save.
- Backend creates a session-level AI job and dispatches it to the AI engine.
- Successful processing stores generated summary, generated report, extracted metadata, report template key, and organization source.
- Previous generated summary/report/metadata snapshots are retained in extracted metadata as recent processed versions so future UI can fall back to earlier output.
- A successful exact national ID match can attach the session to an existing patient.

## Involved Screens

- [Capture](../screens/capture.md)
- [Organize](../screens/organize.md)
- [Session review](../screens/session-review.md)

## Important States

- Draft
- Processing
- Unassigned
- Needs review
- Failed/Retry
- Missing patient information warning

## Related APIs

- `POST /api/v1/sessions/{session_id}/save`
- `POST /api/v1/sessions/{session_id}/retry-processing`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/ai-jobs`

## Known Gaps

- The frontend exposes verify and retry-processing actions, but not reopen or start-review.
- Processing refresh is time-delayed polling rather than live progress.
