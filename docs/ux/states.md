# UX States

## Loading

- Auth bootstrap shows a login-card skeleton while stored credentials refresh.
- Session review shows a skeleton if opened before a session object is available.
- Source previews attempt local cache first, then backend file content; missing media falls back to unavailable placeholders.

## Processing

- New local captures show `Saved on device`, then `Syncing`, then backend-derived states.
- Uploaded captures initially process through backend/AI jobs and can show generated details as pending.
- Capture generated details are expandable:
  - Audio: `Transcription`
  - Photo: `Caption`
  - Text: `Decorated text`
- Saving a session changes the session to processing and queues session-level report generation.
- The frontend schedules a refresh about 5.5 seconds after capture upload or session save.

## Success

- Local capture persistence shows `Saved on device.`
- Successful upload shows `Capture safely transferred.`
- Session save shows `Session processing started.`
- Session title changes show `Session title updated.`
- Session verification shows `Session verified.`
- Session retry shows `Retry started.`
- Session metadata changes show `Metadata updated.`
- Patient assignment shows `Session assigned.`, `Capture assigned.`, or clear-state copy.

## Errors

- Login failures show inline messages.
- Device storage or audio conversion failures show toasts.
- Upload, sync, or save failures show `Failed/Retry`.
- Source preview failures show `Source preview is not available right now.`
- Backend validation and permission errors are returned by the API; the current frontend mostly reduces these to generic failure toasts.

## Empty

- Capture empty state says nothing has been captured yet and prompts audio, photo, or note capture.
- Organize buckets show per-bucket empty copy, such as no draft sessions, no unassigned sessions, or no active processing.
- Patient search shows `No matching patients.`
- Session review capture list shows `No captures loaded for this session yet.`

## Offline And Network Failure

- Captures are saved to IndexedDB before upload.
- A sync safety banner appears when pending captures exist and includes `Retry now`.
- The app warns on browser unload while pending captures exist.
- The outbox retries when the browser comes online and also retries after a delay while pending captures remain.
- If backend session loading fails, the app keeps local pending sessions visible.

## Permission Denied

- Patient-preview users see a limited-access screen.
- Backend 401 responses trigger one token refresh/retry. If refresh fails, local auth is cleared.
- Backend 403 responses do not have a specialized frontend screen.

## Unsaved Data

- Session title edits can be saved explicitly. If the title input loses focus before saving, the draft title resets.
- Unsynced captures are the primary protected unsaved state and are covered by the sync banner plus unload warning.

## Known Gaps

- No dedicated not-found route.
- No detailed permission-denied UI for staff/admin role mismatches.
- No user-facing storage quota warning beyond pending-capture safety copy.
- No explicit retry button for failed capture processing in the current frontend, although the backend capture retry endpoint exists.
- Previous processed session versions are retained in metadata, but there is no restore UI yet.
