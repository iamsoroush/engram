# Capture A Session

## User Goal

Capture clinical material quickly without selecting a patient first.

## Entry Point

- Staff login lands on Active Session.
- Staff can also use bottom capture actions from Clinical Memory or Search.

## Current Behavior

1. User chooses sticky bottom action `Audio`, `Take photo`, or `Write note`. Audio is a direct action labeled `Tap to record`.
2. The relevant dialog/sheet opens:
   - Audio starts microphone recording when supported; otherwise the user can attach an audio file.
   - Photo opens the device camera directly on mobile-style touch devices, then shows the selected image in the photo preview dialog. The dialog also keeps a standard image picker available for gallery/photo-library selection and desktop upload. Photo inputs use the browser's standard image picker/camera format handling.
   - Text opens a note sheet.
3. User saves to the current session or, for photo/text, saves into a new session.
   - Users may assign patient context before the first capture; this creates a local empty workspace context and the assignment is applied to the backend session after the first capture syncs.
4. The browser standardizes the draft, creates a local capture/session, and writes it to IndexedDB.
5. The Active Session screen shows the local session immediately.
6. The app makes captures available beyond the device when authenticated and online.
7. Uploaded captures are merged with remote IDs and local preview cache is retained.
8. The draft report updates immediately with capture-specific progressive lines:
   - audio: inline playback plus `Audio capture saved. Organizing.`
   - photo: inline photo preview plus `Photo saved. Organizing.`
   - text: formatted note content
9. Draft capture cards show source preview/playback, assistant-style saved or organizing text when relevant, and full generated text when available. Completed captures do not show technical status in the card. Audio transcripts and photo captions are fully visible inline and indicate whether the text is assistant-generated or staff-edited; note captures show full decorated text and an expandable raw note.
10. Users can rename or delete a capture from the capture item settings menu. Deleting a capture removes it from the live draft and returns any generated structured report to draft/stale state.
11. Structured report navigation becomes available after the first capture exists; before that it stays disabled with guidance to create a capture first.
12. Adding, deleting, or changing patient context after a structured report exists returns report progress to `Draft` until the user generates again.
13. If the browser refreshes, the app restores the active workspace from local workspace state plus pending/backend sessions when possible.

## System Behavior

- Local storage happens before network-dependent work.
- Active workspace state is stored locally as a lightweight continuity snapshot.
- First remote upload creates a draft session when no remote session is supplied.
- The system stores the source artifact and starts organization when available.
- The frontend keeps local progressive draft output visible while generated output becomes available.

## Involved Screens

- [Active Session](../screens/capture.md)
- [Session review](../screens/session-review.md), when reviewing captured material later

## Important States

- `Saved`
- `Organizing`
- `Saved on this device`
- `Needs your input`
- `Memory updated`

## Related APIs

- `POST /api/v1/captures`
- `POST /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- Audio recording requires browser media support and may need HTTPS on phones.
- Critical local-save or storage warnings still need a polished recovery path.
- Workspace continuity is a local UX snapshot, not yet a complete production offline model.
