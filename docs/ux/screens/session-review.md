# Session Review

## Route

No separate route. Opens as a dialog over `/#organize`.

## Purpose

Review one processed session, inspect generated outputs and captures, edit title and metadata, assign patients, retry failed processing, add captures, and verify eligible sessions.

## Primary Actions

- Verify eligible unassigned or needs-review sessions.
- Add capture to reopen the session as a draft with stale generated output.
- Save title and editable metadata.
- Save or retry processing when eligible.
- Search patients.
- Create patient with name and optional national ID.
- Assign selected patient to the session.
- Clear session patient.
- Assign or override patient on a capture.
- Open capture source preview.

## Visible Data

- Session title, full summary, status, and patient assignment.
- Generated report.
- Editable patient full name and national ID.
- Flexible editable extracted metadata JSON.
- Extracted metadata highlights such as visit type and body area when available.
- Missing patient-information warning when metadata includes missing fields.
- Patient search results.
- Expandable capture list with source previews, statuses, generated details, and assignment state.

## Main Components

- `SessionDetail`
- `SessionGeneratedOutputs`
- `PatientAssignmentPanel`
- `CaptureItemCard`
- `SourcePreviewDialog`

## Loading State

- Skeleton if the dialog renders without a session.
- Captures are loaded on open when a backend session has no items.

## Empty State

- `No captures loaded for this session yet.`
- `No matching patients.`
- Generated report area says to save the draft session when no report exists.
- Stale generated output is clearly labeled after a capture is added to previously processed material.

## Error State

- Assignment, title, verify, retry, and metadata failures generally surface through unchanged UI or generic failure patterns; there is no detailed inline assignment error.
- Source preview failures show inline preview error.

## Success State

- Title and assignment actions update visible session/capture state and show success toasts.
- Generated outputs appear after session processing succeeds.
- Verify moves eligible sessions to `verified`.

## Related Workflows

- [Save and organize a session](../workflows/save-and-organize-session.md)
- [Review and assign patients](../workflows/review-and-assign-patients.md)

## Related APIs

- `GET /api/v1/sessions/{session_id}/captures`
- `PATCH /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/save`
- `POST /api/v1/sessions/{session_id}/retry-processing`
- `POST /api/v1/sessions/{session_id}/verify`
- `GET /api/v1/patients`
- `POST /api/v1/patients`
- `POST /api/v1/sessions/{session_id}/assign-patient`
- `POST /api/v1/captures/{capture_id}/assign-patient`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- Reopen and start-review backend actions are not exposed in the current frontend.
- The dialog does not have its own shareable URL.
