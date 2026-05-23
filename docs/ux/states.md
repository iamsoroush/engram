# UX States

## Session State Badges

Session states are informational badges, not workflow gates.

The frontend maps backend session statuses into six user-facing states:

- `Capturing`
- `Processing`
- `Needs review`
- `Unassigned`
- `Verified`
- `Failed`

Sessions remain openable from Patients and Search in all states. Verification and organization states should not control visibility or review access.

`Draft`, `Current session`, and `Reopened` are shown as `Capturing`. `Organized` and `In review` are shown as `Needs review`.


## Loading

- Auth bootstrap shows a login-card skeleton while stored credentials refresh.
- Active workspace continuity is restored from a lightweight local snapshot after auth refresh when possible.
- Historical review loads captures inline if a selected backend session has no capture items yet.
- Source previews attempt local cache first, then backend file content; missing media falls back to unavailable placeholders.

## Processing

- New local captures show animated `Syncing...`, then animated `Processing...` while backend work is active. Completed capture cards do not show a status.
- Uploaded captures initially process through backend/AI jobs and can show generated details as pending.
- Capture generated details are expandable:
  - Audio: `Transcription`
  - Photo: `Caption`
  - Text: `Decorated text`
- Capture upload updates deterministic local session report, summary, findings, and processing-status contracts.
- Generating a structured report can change the session to processing and start session-level report generation.
- The frontend schedules a short bounded refresh series after capture upload or structured report generation so asynchronous backend stages can appear over time.
- The report area never becomes a full-screen loading state; it keeps the same layout while moving through empty, partial, structured, and verified states.

## Success

- Local capture persistence shows `Saved on device.`
- Successful upload shows `Capture safely transferred.`
- Structured report generation shows `Structured report is generating.`
- Session title changes show `Session title updated.`

## Errors

- Login failures show inline messages.
- Device storage or audio conversion failures show toasts.
- Upload, sync, or save failures show `Failed`.
- Source preview failures show `Source preview is not available right now.`
- Backend validation and permission errors are returned by the API; the current frontend mostly reduces these to generic failure toasts.

## Empty

- Active Session with no captures still shows the workspace and empty report surface.
- Patients shows empty copy for patient-linked sessions and unassigned sessions.
- Search shows empty copy before a query and when no loaded memory matches.
- Session review capture list shows `No captures loaded for this session yet.`

## Offline And Network Failure

- Captures are saved to IndexedDB before upload.
- A sync safety banner appears when pending captures exist and includes `Retry now`.
- The app warns on browser unload while pending captures exist.
- The outbox retries when the browser comes online and also retries after a delay while pending captures remain.
- If backend session loading fails, the app keeps local pending sessions visible.
- The active session, selected historical session, assignment form target, destination chooser, and current report/capture structure are restored from local workspace state when possible.

## Permission Denied

- Patient-preview users see a limited-access screen.
- Backend 401 responses trigger one token refresh/retry. If refresh fails, local auth is cleared.
- Backend 403 responses do not have a specialized frontend screen.

## Unsaved Data

- Session title edits can be saved explicitly. If the title input loses focus before saving, the draft title resets.
- Unsynced captures are the primary protected unsaved state and are covered by the sync banner plus unload warning.
- Interrupted assignment and capture-destination choices are restored as lightweight UI state after refresh when possible.

## Known Gaps

- No dedicated not-found route.
- No detailed permission-denied UI for staff/admin role mismatches.
- No user-facing storage quota warning beyond pending-capture safety copy.
- Failed local uploads and failed capture processing expose per-capture retry actions from the capture overflow menu.
- Previous processed session versions are retained in metadata, but there is no restore UI yet.
