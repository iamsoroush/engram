# Review And Assign Patients

## User Goal

Review processed session material, inspect generated output, assign patients, verify sessions, and continue capture without a modal-heavy workflow.

## Entry Point

- Patients or Search processed-session row opens inline historical review.
- Patients or Search draft row opens the Active Session screen directly.

## Current Behavior

1. User opens Patients or Search.
2. Sessions appear in patient-centered memory sections, unassigned work, or local search results.
3. User selects a session row.
4. Inline historical review opens with title editing, status, report, summary, extracted findings, add-capture action, and expandable captures.
5. If captures are not already loaded and the session is a backend session, the frontend loads them.
6. User can assign a patient from a compact inline form on a Patients card or from the Session Workspace search sheet.
7. User can verify the session from the Patients card or Session Workspace.
8. User can add capture material, which returns the same session to the Active Session workspace and refreshes progressive output.
9. Session and capture cards remain reviewable in place.

## System Behavior

- Adding capture material to processed output keeps the same session usable and updates deterministic progressive contracts.
- Assignment uses the Session Workspace bottom sheet with suggested matches, search by name, phone, or national ID, creates a lightweight patient record inline with optional national ID when needed, and assigns the session.
- Verification updates the session state without blocking later review or capture.

## Involved Screens

- [Patients](../screens/patients.md)
- [Search](../screens/search.md)
- [Session review](../screens/session-review.md)

## Important States

- Unassigned
- Needs review
- Verified
- Stale generated output
- Missing patient information, when present in existing metadata

## Related APIs

- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/patients`
- `POST /api/v1/patients`
- `POST /api/v1/sessions/{session_id}/assign-patient`
- `POST /api/v1/sessions/{session_id}/verify`

## Known Gaps

- Duplicate patient review is still lightweight; the current UI prefers fast assignment over modal-heavy matching.
- Processed-output versions are retained in metadata, but there is not yet a dedicated UI for restoring a previous version.
- Patient cards are still derived from loaded sessions rather than a dedicated patient timeline API.
