# Active Session Workspace

## Route

- `/`
- `/#active-session`
- `/#capture`, legacy fallback

## Purpose

Primary working screen for building and reviewing a session from audio, photo, and text captures. The same workspace structure is reused for historical session review from Patients and Search.

## Primary Actions

- Record audio.
- Take photo. On mobile-style touch devices, this action opens the device camera directly before the photo preview dialog; the preview dialog still supports gallery/photo-library selection.
- Write note.
- Rename current session.
- Assign or reassign patient.
- Generate Structured Report from the report header.
- Verify session.
- Start a new session.
- Review a historical session inline from Patients or Search.
- Add capture from historical review, which returns the same session to the active workspace.
- Open a source preview.

## Visible Data

- Session header with compact title, session state, and new-session action.
- Report header with `Clinical Report`, centered passive status, Generate action, and animated verification checkbox.
- Report toolbar with a single actionable patient selector before the view switch.
- Assigned patient controls show smaller assignment source text under the patient name only when a patient exists.
- Patient assignment opens a lightweight centered modal with live search/autocomplete and inline patient creation.
- Clinical report section that always exists, including before the first capture.
- Live mocked draft capture cards that update immediately when audio, photo, or text captures are added.
- Audio captures render playback inline in the draft.
- Photo captures render inline in the draft with caption/analysis text beneath the image.
- Structured reports show photos as evidence inside the report body and avoid repeating photo captions in the generated body text.
- Source captures are no longer duplicated in a separate expandable section; the live draft cards are the source review surface.
- The live draft remains reviewable after structured report generation starts; users can switch between `Live draft` and `Structured report`.
- Mocked progressive report states: `Empty draft`, `Partial draft`, `Structured report`, and `Verified report`.
- Subtle report progress indicators for `Draft`, `Structured`, and `Verified` in the report header.
- Collapsible summary.
- Collapsible extracted findings.
- Capture source previews.
- Capture status badges.
- Expandable generated transcript/caption/decorated text.
- Sync safety banner when pending captures exist.

## Main Components

- `Shell`
- `CaptureActions`
- `CaptureScreen`
- `TextCaptureSheet`
- `PhotoPreviewDialog`
- `AudioDialog`
- `SourcePreviewDialog`

## Loading State

- Source previews load cached blobs first, then protected backend file content.
- When pending local captures exist, staff can retry sync or clear device-only pending capture data from the sync safety banner.

## Empty State

- Active mode with no captures still shows the Active Session Workspace and an empty report surface.
- Historical review with no loaded captures shows the empty live draft surface.

## Error State

- Toasts for storage, audio conversion, sync, save, and processing failures.
- Empty photo selections are rejected before save/upload and prompt the user to open the camera or gallery again.
- Clearing local pending capture data removes browser-only outbox/cache records and returns the device to the backend-backed state.
- A failed pending capture does not block later pending captures; later items continue syncing, and failed items remain for a later retry.
- Source preview unavailable placeholder or inline preview error.

## Success State

- Capture appears immediately after local save.
- Toasts confirm local save, safe transfer, title update, assignment, and structured report generation start.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Generate structured session report](../workflows/save-session.md)

## Related APIs

- `POST /api/v1/captures`
- `POST /api/v1/sessions/{session_id}/save`
- `POST /api/v1/sessions/{session_id}/assign-patient`
- `POST /api/v1/sessions/{session_id}/verify`
- `GET /api/v1/patients`
- `POST /api/v1/patients`
- `PATCH /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- No per-capture manual retry control in the feed.
- `+ New session` resets the active context but does not create an empty backend session until a capture syncs.
- Report, summary, extracted findings, and processing status use stable backend contracts plus mocked live draft output until final AI session artifacts are integrated.
- Report layout keeps a stable body height during mocked processing so captures remain visible below instead of being displaced by loading states.
- Historical review currently shares the report workspace but does not yet expose the full patient assignment panel.
