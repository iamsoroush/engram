# UX Overview

## Summary

AesMem is a capture-first clinical assistant for aesthetics clinics. The current implemented UX lets authenticated clinic staff capture audio, photo, or text immediately, keep those captures safe in the browser while syncing, progressively evolve session report output, and review loaded session memory through the new Active Session, Patients, and Search shell.

The UX keeps capture first while moving long-term review toward patient-centered memory. Patient assignment remains non-blocking and is being reintegrated into the inline review workspace.

## Main Users

- Doctor: captures clinical material and reviews generated session output.
- Assistant: captures, assigns patients, and reviews session memory.
- Admin: can load staff-facing session lists, but cannot perform staff-only capture or assignment APIs.
- Patient preview: receives a limited-access screen only; staff tools are unavailable.

## Main Workflows

- [Capture a session](workflows/capture-session.md)
- [Generate structured session report](workflows/save-session.md)
- [Review and assign patients](workflows/review-and-assign-patients.md)

## Main Screens

- [Login](screens/login.md)
- [Capture / Active Session](screens/capture.md)
- [Patients](screens/patients.md)
- [Search](screens/search.md)
- [Session review](screens/session-review.md)

## Navigation Summary

The prototype is a single React app with hash-based screen selection:

- Default: Active Session Workspace
- `#active-session`: current active session workspace
- `#patients`: patient-centered memory and unassigned sessions
- `#search`: local memory search

The shell keeps Active Session, Patients, and Search available in the top-left navigation after staff login. Capture actions are always available as bottom pills for staff users.

See [navigation](navigation.md).

## Important UX Constraints

- Capture must not require selecting a patient.
- Local persistence happens before network upload.
- Unsynced captures remain visible and warn the user not to clear browser data.
- Generated capture/session output is shown as review material with lightweight confidence and state indicators.
- Technical AI pipeline labels are mostly hidden behind user-facing states such as `Processing`, `Unassigned`, `Needs review`, and `Failed`.
- Backend OpenAPI remains the source of truth for exact API contracts.
