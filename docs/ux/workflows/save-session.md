# Generate Structured Session Report

## User Goal

Generate structured session output from the live draft while keeping the Active Session Workspace usable. Report, summary, and extracted-finding contracts already exist and evolve as captures are added.

## Entry Point

- Active Session `Generate Structured Report` button on a synced capturable session.

## Current Behavior

1. User captures one or more items.
2. Local sessions must finish syncing before save is available; the button reads `Syncing first`.
3. User selects `Generate Structured Report`.
4. The frontend calls the backend save endpoint with the default report template key.
5. The session moves to `Processing`.
6. The frontend shows a subtle generation toast and schedules progressive polling.
7. The live draft remains available as a switchable report view while structured output is generating.
8. When processing succeeds, Patients shows the session in patient-linked memory when a patient is assigned, otherwise in `Unassigned sessions`.
9. Inline historical review shows the generated report, summary, extracted findings, and source captures when present.
10. If a user adds capture material after processing, the same session receives deterministic progressive report, summary, finding, and processing-status updates.

## System Behavior

- Backend accepts structured report generation attempts in any session state.
- Sessions without captures return the current session contract without queuing processing.
- Backend creates a session-level AI job and dispatches it to the AI engine.
- Successful processing stores generated summary, generated report, extracted metadata, report template key, and backend organization metadata.
- Previous generated summary/report/metadata snapshots are retained in extracted metadata so future UI can recover earlier output.
- A successful exact national ID match can attach the session to an existing patient.

## Involved Screens

- [Active Session](../screens/capture.md)
- [Patients](../screens/patients.md)
- [Search](../screens/search.md)
- [Session review](../screens/session-review.md)

## Important States

- Capturing
- Processing
- Unassigned
- Needs review
- Verified
- Failed
- Missing patient information warning

## Related APIs

- `POST /api/v1/sessions/{session_id}/save`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/ai-jobs`

## Known Gaps

- Inline historical review does not yet expose retry-processing, reopen, or start-review actions.
- Structured report progress is time-delayed polling plus mocked inline draft evolution rather than live AI progress.
- TODO: Remove backend `organizationSource` naming once backend state and memory APIs align with the Active Session/Patients model.
