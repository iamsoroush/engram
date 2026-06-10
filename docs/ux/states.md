# UX States

## Assistant-State Language

Memora should translate technical system work into calm assistant language.

Preferred user-facing states:

- `Saved`
- `Syncing`
- `Uploading`
- `Processing`
- `Organizing`
- `Needs your input`
- `In progress`
- `Verified`
- `Updated today`
- `Storage warning`

Avoid normal user-facing labels such as:

- AI failed
- retry AI
- retry sync
- upload queue
- backend unavailable
- job pending
- transcription retry

Sync and AI retry are system responsibilities, not user responsibilities.

## Session State Badges

Session states are informational, not workflow gates.

Use plain clinical-memory language:

- `Capturing`, when the user is actively adding material.
- `Saved`, when capture material is safely stored.
- `Organizing`, when the system is preparing summaries or memory updates.
- `Processing`, when a capture is available to the backend and generated details are being prepared.
- `Needs your input`, when human judgment is required.
- `Memory updated`, when the session is reflected in patient memory.
- `Syncing` or `Uploading`, when the material is local and safe but not fully available everywhere yet.

Do not show `Failed` as a default state in normal memory surfaces. If something requires attention, translate it into either human decision copy or a data-safety warning.

## Loading

- Auth bootstrap shows a login-card skeleton while stored credentials refresh.
- Active workspace continuity is restored from a lightweight local snapshot after auth refresh when possible.
- Historical review loads captures inline if a selected session has no capture items yet.
- Source previews attempt local cache first, then remote file content; missing media falls back to unavailable placeholders.
- Loading should not replace the report or memory surface with a full-screen waiting state when saved content is already available.

## Organizing

- New captures confirm local safety first with `Syncing` or `Uploading`, then show `Processing` while generated details improve. Type-specific assistant language, such as `Transcribing audio`, belongs inside the generated transcript/caption area.
- Capture generated details are expandable:
  - Audio: `Transcription`
  - Photo: `Caption`
  - Text: `Decorated text`
- The report area always exists and can move through empty, partial, summarized, and reviewed states without blocking capture.
- If AI is unavailable, use available deterministic or rule-based text and update memory later.

## Success

Examples:

- `Saved.`
- `Uploading.`
- `Memory updated.`
- `Summary is ready for your review.`
- `Patient memory updated.`

## Errors And Warnings

Only interrupt the user when human input is required or local data safety is at risk.

Use human-readable warnings:

- `Device storage is almost full. Free space so new captures stay safe.`
- `This visit is saved. Choose which patient it belongs to.`
- `I found a likely patient match. Confirm before I update memory.`
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

- `Offline · Captures are saved on this device`
- `Saving on this device`
- `3 captures saved on this device. I'll organize them when connection returns.`
- `You're offline. Patient search may be limited.`
- `Storage is getting full. New offline captures may not be safely saved soon.`

Do not show normal UI actions for manual sync retry, upload retry, queue management, or backend recovery. Clear-cache or local reset tooling belongs behind debug/admin settings, not in the normal clinician UI. The system should sync when connectivity returns.

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

Needs input contains only **critical** human-decision items, in three patient/AI categories plus one
data-safety category. The categories are computed by the backend (the single source of truth shared
by the patient-card needs-input badge and the Needs input tab, so they always agree):

- **assign patient** — an unassigned visit with no usable candidate.
- **choose patient** — an ambiguous/uncertain auto-match (a possible match, a national-ID conflict,
  or a tie) on an unassigned visit.
- **verify patient** — an AI-created patient record awaiting staff verification before it enters memory.
- **storage warning** — a critical storage or local-save data-safety warning (client-side).

Routine summary confirmation is **not** a needs-input item: a processed, assigned visit with a current
report needs no input. Summary review remains available when a user opens a visit.

Needs input must not contain:

- AI job failed
- retry transcription
- retry sync
- backend unavailable
- upload queue
- job status debug information

Each item should have one primary action that opens the smallest resolver needed to complete the decision. It must not use the active session page as the primary destination.

Needs-input cards must answer:

- what decision is needed
- which session or visit is involved
- which patient is involved, if known
- why input is needed
- the focused action that resolves it

Use exact labels such as `Needs input: assign patient`, `Needs input: choose patient`, or `Needs input: verify patient`. Do not use vague labels such as `Needs input` or `Review` without explaining what kind of input is required.

Resolver routing:

- `Assign patient` opens patient assignment.
- `Choose patient` opens patient choice (also used for a national-ID conflict).
- `Verify patient` opens the visit in Active Session, where the AI-created-patient verify panel confirms the record.
- `Review storage` opens storage guidance or review.
- `Open visit` may be secondary.

## Time Labels

Timestamp labels must make the timestamp type explicit whenever session time, update time, and needs-input time can coexist.

Use:

- `Session: Today · 4:23 PM`
- `Updated: 4:31 PM`
- `Session: Apr 18 · 11:30 AM`
- `Updated today · Patient assigned`
- `Needs input since: 2:20 PM`

Avoid ambiguous labels such as `Today · 4:23 PM` or `Updated today` when the UI does not clarify whether it is session time, update time, or needs-input time.

## Unsaved Data

- Captures must be saved locally before network-dependent work begins.
- The persistent capture bar is the trust anchor: it tells the user where captures will go and whether they are safely saved.
- Browser unload warnings are acceptable when leaving could risk device-only work.
- Critical storage/local-save warnings may appear in Needs input because they affect data safety.

## Known Gaps

- No dedicated not-found route.
- No detailed permission-denied UI for staff/admin role mismatches.
- Critical browser storage quota handling needs a polished warning and recovery path.
