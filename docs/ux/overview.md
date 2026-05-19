# UX Overview

## Summary

AesMem is a capture-first clinical assistant for aesthetics clinics. The current implemented UX lets authenticated clinic staff capture audio, photo, or text immediately, keep those captures safe in the browser while syncing, save a draft session for generated report output, and review unassigned or needs-review sessions later.

The UX intentionally avoids patient-first navigation. Patient assignment happens during review and does not block capture.

## Main Users

- Doctor: captures clinical material and reviews generated session output.
- Assistant: captures, organizes, assigns patients, and reviews sessions.
- Admin: can load staff-facing session lists, but cannot perform staff-only capture or assignment APIs.
- Patient preview: receives a limited-access screen only; staff tools are unavailable.

## Main Workflows

- [Capture a session](workflows/capture-session.md)
- [Save and organize a session](workflows/save-and-organize-session.md)
- [Review and assign patients](workflows/review-and-assign-patients.md)

## Main Screens

- [Login](screens/login.md)
- [Capture](screens/capture.md)
- [Organize](screens/organize.md)
- [Session review](screens/session-review.md)

## Navigation Summary

The prototype is a single React app with hash-based screen selection:

- Default: `Capture`
- `#capture`: current capture session
- `#organize`: session buckets and review entry point

The shell keeps Capture and Organize available in the top navigation after staff login. Capture actions are always available as bottom pills for staff users.

See [navigation](navigation.md).

## Important UX Constraints

- Capture must not require selecting a patient.
- Local persistence happens before network upload.
- Unsynced captures remain visible and warn the user not to clear browser data.
- Generated capture/session output is shown as unverified review material until staff verifies it.
- Technical AI pipeline labels are mostly hidden behind user-facing states such as `Processing`, `Unassigned`, `Needs review`, and `Failed/Retry`.
- Backend OpenAPI remains the source of truth for exact API contracts.
