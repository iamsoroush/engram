# Review And Assign Patients

## User Goal

Review processed session material, inspect generated output, edit flexible metadata, associate the session or individual captures with a patient, and verify the session.

## Entry Point

- Organize processed-session row opens the session review dialog.
- Organize draft row opens the Capture screen directly.

## Current Behavior

1. User opens Organize.
2. Sessions are grouped by status buckets.
3. User selects a session row.
4. Session review dialog opens with title editing, status, full summary, verify/add-capture actions, generated outputs, editable metadata, patient assignment, and expandable captures.
5. If captures are not already loaded and the session is a backend session, the frontend loads them.
6. User searches existing patients as they type or creates a patient with name and optional national ID.
7. User can assign the selected patient to the full session.
8. User can assign or override the selected patient on individual captures.
9. User verifies an eligible unassigned or needs-review session.
10. Session and capture cards update in place and success toasts confirm assignment or verification.

## System Behavior

- Session assignment can also fill unassigned captures in that session.
- Assigning a patient to an unassigned session moves it to needs review on the backend.
- Adding capture material to processed output returns the session to draft and marks generated output stale until the next save/process cycle.
- Patient search matches names, contact details, and identifiers within the current tenant.
- Patient creation writes searchable identifiers for national ID, phone, email, display name, and birth date when provided.

## Involved Screens

- [Organize](../screens/organize.md)
- [Session review](../screens/session-review.md)

## Important States

- Unassigned
- Needs review
- Verified
- Stale generated output
- Missing patient information
- No matching patients

## Related APIs

- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/patients`
- `POST /api/v1/patients`
- `POST /api/v1/sessions/{session_id}/assign-patient`
- `POST /api/v1/sessions/{session_id}/verify`
- `POST /api/v1/captures/{capture_id}/assign-patient`

## Known Gaps

- Patient creation in the current UI only captures display name and national ID.
- Processed-output versions are retained in metadata, but there is not yet a dedicated UI for restoring a previous version.
- There is no dedicated patient record screen in the active app route, despite some unused prototype screen files.
