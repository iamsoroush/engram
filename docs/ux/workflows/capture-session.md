# Capture A Session

## User Goal

Capture clinical material quickly without selecting a patient first.

## Entry Point

- Staff login lands on Capture.
- Staff can also use bottom capture actions from Organize.

## Current Behavior

1. User chooses `Record audio`, `Take photo`, or `Write note`.
2. The relevant dialog/sheet opens:
   - Audio starts microphone recording when supported; otherwise the user can attach an audio file.
   - Photo opens the device camera directly on mobile-style touch devices, then shows the selected image in the photo preview dialog. The dialog also keeps a standard image picker available for gallery/photo-library selection and desktop upload. Photo inputs use the browser's standard image picker/camera format handling.
   - Text opens a note sheet.
3. User saves to the current session or, for photo/text, saves into a new session.
4. The browser standardizes the draft, creates a local capture/session, and writes it to IndexedDB.
5. The active Capture screen shows the local session immediately.
6. The outbox uploads captures one at a time when authenticated and online.
7. Uploaded captures are merged with backend IDs and local preview cache is retained.
8. Capture cards show source preview, status badge, and expandable generated text area.

## System Behavior

- Local storage happens before network upload.
- First backend upload creates a draft session when no backend session is supplied.
- Backend stores the source artifact and queues a capture processing job.
- The frontend refreshes captures after a short delay to pick up generated placeholder output.

## Involved Screens

- [Capture](../screens/capture.md)
- [Session review](../screens/session-review.md), when reviewing captured material later

## Important States

- `Saved on device`
- `Syncing`
- `Processing`
- `Processed`
- `Needs review`
- `Failed/Retry`

## Related APIs

- `POST /api/v1/captures`
- `POST /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- Audio recording requires browser media support and may need HTTPS on phones.
- Failed sync has generic recovery copy and no per-capture detailed error.
