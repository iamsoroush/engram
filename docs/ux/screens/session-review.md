# Session Review

## Route

No separate route. Opens inline over `/#patients` or `/#search` using the Active Session Workspace structure.

## Purpose

Review one session with the same report-first structure used by the active workspace, inspect generated output and captures, edit the title, and add captures to the same evolving session.

All session states remain reviewable. State badges are informational and do not gate historical review access.

## Primary Actions

- Add capture to continue the same session with refreshed progressive output.
- Save title.
- Open capture source preview.

## Visible Data

- Session title, full summary, status, and actionable patient assignment.
- Clinical report with mocked progressive state, passive status indicators, and live draft/structured view switching when backend report output is unavailable.
- Collapsible summary.
- Collapsible extracted findings.
- Source previews, statuses, and generated capture details through clickable live draft cards.

## Main Components

- `CaptureScreen`, historical mode
- `SourcePreviewDialog`

## Loading State

- Captures are loaded on open when a backend session has no items.

## Empty State

- `No captures loaded for this session yet.`
- Generated report area remains visible when no processed report exists.
- Progressive output is refreshed after a capture is added to previously processed material.

## Error State

- Title failures generally surface through unchanged UI or generic failure patterns.
- Source preview failures show inline preview error.

## Success State

- Title actions update visible session state and show success toasts.
- Generated outputs appear after session processing succeeds.

## Related Workflows

- [Generate structured session report](../workflows/save-session.md)
- [Review and assign patients](../workflows/review-and-assign-patients.md)

## Related APIs

- `GET /api/v1/sessions/{session_id}/captures`
- `PATCH /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/save`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- Retry and editable metadata controls are not yet reintegrated into the inline workspace.
- Historical review does not have its own shareable URL.
