# UX States

## Assistant-State Language

AesMem should translate technical system work into calm assistant language.

Preferred user-facing states:

- `Saved`
- `Organizing`
- `Needs your input`
- `Saved on this device`
- `Memory updated`
- `Offline - captures are saved on this device`

Avoid normal user-facing labels such as:

- AI failed
- AI engine down
- job retrying
- sync pending
- upload retry
- backend unavailable
- queue length

Sync and AI retry are system responsibilities, not user responsibilities.

## Session State Badges

Session states are informational, not workflow gates.

Use plain clinical-memory language:

- `Capturing`, when the user is actively adding material.
- `Saved`, when capture material is safely stored.
- `Organizing`, when the system is preparing summaries or memory updates.
- `Needs your input`, when human judgment is required.
- `Memory updated`, when the session is reflected in patient memory.
- `Saved on this device`, when the material is local and safe but not fully available everywhere yet.

Do not show `Failed` as a default state in normal memory surfaces. If something requires attention, translate it into either human decision copy or a data-safety warning.

## Loading

- Auth bootstrap shows a login-card skeleton while stored credentials refresh.
- Active workspace continuity is restored from a lightweight local snapshot after auth refresh when possible.
- Historical review loads captures inline if a selected session has no capture items yet.
- Source previews attempt local cache first, then remote file content; missing media falls back to unavailable placeholders.
- Loading should not replace the report or memory surface with a full-screen waiting state when saved content is already available.

## Organizing

- New captures confirm local safety first, then may show `Organizing` while summaries or memory updates improve.
- Capture generated details are expandable:
  - Audio: `Transcription`
  - Photo: `Caption`
  - Text: `Decorated text`
- The report area always exists and can move through empty, partial, summarized, and reviewed states without blocking capture.
- If AI is unavailable, use available deterministic or rule-based text and update memory later.

## Success

Examples:

- `Saved.`
- `Saved on this device.`
- `Memory updated.`
- `Summary is ready for your review.`
- `Patient memory updated.`

## Errors And Warnings

Only interrupt the user when human input is required or local data safety is at risk.

Use human-readable warnings:

- `Device storage is almost full. Free space so new captures stay safe.`
- `This visit is saved. Choose which patient it belongs to.`
- `I found two possible patient matches. Confirm before I update memory.`
- `Source preview is not available right now.`

Avoid exposing backend validation, AI job, upload, or sync details unless the user must act to keep data safe.

## Empty

- Active Session with no captures still shows the workspace and empty report surface.
- Clinical Memory Today shows calm current-work copy instead of a blank dashboard.
- Clinical Memory Patients shows searchable empty copy when no patient memory is available.
- Clinical Memory Needs input says there is nothing urgent when no human decisions are waiting.
- Search shows empty copy before a query and when no loaded memory matches.
- Session review capture list shows `No captures loaded for this session yet.`

## Offline And AI-Unavailable Behavior

Offline mode should reassure the user that capture can continue.

User-facing copy examples:

- `Offline - captures are saved on this device.`
- `Saving on this device.`
- `Search may show only patients saved on this device.`

Do not show normal UI actions for manual sync retry, upload retry, queue management, or backend recovery. The system should sync when connectivity returns.

AI-unavailable mode should be mostly invisible:

- capture still works
- saved material remains reviewable
- summaries can use fallback language
- the system updates memory when AI becomes available

Acceptable copy:

- `Saved. I will update memory when ready.`
- `Organizing when available.`

Do not put AI retry, transcription retry, or processing failure tasks in Needs input.

## Needs Input Rules

Needs input contains only human-decision items:

- unassigned visit
- uncertain patient match
- summary ready for confirmation
- critical storage or local-save warning

Needs input must not contain:

- AI job failed
- retry transcription
- retry sync
- backend unavailable
- upload queue
- job status debug information

Each item should have one primary action.

## Unsaved Data

- Captures must be saved locally before network-dependent work begins.
- The persistent capture bar is the trust anchor: it tells the user where captures will go and whether they are safely saved.
- Browser unload warnings are acceptable when leaving could risk device-only work.
- Critical storage/local-save warnings may appear in Needs input because they affect data safety.

## Known Gaps

- No dedicated not-found route.
- No detailed permission-denied UI for staff/admin role mismatches.
- Critical browser storage quota handling needs a polished warning and recovery path.
