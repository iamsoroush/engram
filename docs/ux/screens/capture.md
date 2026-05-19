# Capture Screen

## Route

- `/`
- `/#capture`

## Purpose

Primary working screen for building the current session from audio, photo, and text captures.

## Primary Actions

- Record audio.
- Take photo. On mobile-style touch devices, this action opens the device camera directly before the photo preview dialog; the preview dialog still supports gallery/photo-library selection.
- Write note.
- Save session.
- Rename current session.
- Start a new session.
- Open a source preview.

## Visible Data

- Active session title.
- Current session capture feed.
- Capture source previews.
- Capture status badges.
- Expandable generated transcript/caption/decorated text.
- Sync safety banner when pending captures exist.

## Main Components

- `Shell`
- `CaptureActions`
- `CaptureScreen`
- `CaptureItemCard`
- `TextCaptureSheet`
- `PhotoPreviewDialog`
- `AudioDialog`
- `SourcePreviewDialog`

## Loading State

- Source previews load cached blobs first, then protected backend file content.
- When pending local captures exist, staff can retry sync or clear device-only pending capture data from the sync safety banner.

## Empty State

- `Nothing captured yet` with prompt to start audio, photo, or note capture.

## Error State

- Toasts for storage, audio conversion, sync, save, and processing failures.
- Empty photo selections are rejected before save/upload and prompt the user to open the camera or gallery again.
- Clearing local pending capture data removes browser-only outbox/cache records and returns the device to the backend-backed state.
- A failed pending capture does not block later pending captures; later items continue syncing, and failed items remain for a later retry.
- Source preview unavailable placeholder or inline preview error.

## Success State

- Capture appears immediately after local save.
- Toasts confirm local save, safe transfer, title update, and session processing start.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Save and organize a session](../workflows/save-and-organize-session.md)

## Related APIs

- `POST /api/v1/captures`
- `POST /api/v1/sessions/{session_id}/save`
- `PATCH /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- No per-capture manual retry control in the feed.
- `+ New session` resets the active context but does not create an empty backend session until a capture syncs.
