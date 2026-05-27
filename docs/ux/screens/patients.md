# Clinical Memory Screen

## Route

- `/#patients`

## Purpose

Clinical Memory replaces the old Patients view. It is the main patient-memory surface, but it should feel like a calm clinical assistant rather than a patient table, database browser, or sync console.

The screen optimizes for what matters now:

- today's active or recent visit
- items that need human judgment
- searchable patient memory
- recent memory updates

It must not show every session nested under every patient. Sessions belong in patient detail and timeline views.

## Structure

- Top app bar.
- Page title: `Clinical Memory`.
- Assistant-style subtitle, for example `Your captures are saved. I will organize them into patient memory as details become clear.`
- Search.
- Tabs: `Today`, `Patients`, `Needs input`.
- Persistent bottom capture bar.

## Today Tab

Today is the default landing tab.

It shows:

- one current visit card when an active capture destination exists
- a compact `Needs your input` preview when human judgment is required
- 2-3 recent memory rows with assistant-style summaries
- calm saved-state language and capture chips such as `3 photos`, `1 audio`, `1 note`

It does not show all patients or all sessions.

Today includes only sessions created, captured, or updated on the user's current calendar day. Older unassigned or historical sessions belong in Patients, Search, or the full Needs input surface, not in the Today preview.

The current visit card uses natural assistant copy. If the visit has a patient, show the patient name; otherwise show `Unassigned visit`. Use one primary action per card, such as `Continue`, `Assign patient`, `Review`, or `Open`.

Choosing `Assign patient` from Today opens the same patient assignment form in Clinical Memory without navigating away from the tab. Suggested matches come from patient search data; do not use mock patient suggestions in production UI.

Example copy:

- `Memory updated for Sara M.`
- `Saved. Organizing the visit notes.`
- `1 visit needs your input.`
- `No active visit. Start with audio, photo, or note.`
- `All caught up.`
- `Recent patients will appear here.`

## Patients Tab

Patients is a searchable, scalable list of patient memory.

The backend source for this list is `GET /api/v1/patient-memory`. The endpoint
returns flat patient-memory rows with summary fallbacks, latest-session metadata,
session counts, active-session markers, and pagination. The frontend should not
derive this tab by loading every session and grouping client-side.

Each patient row/card includes:

- patient name and compact identifying context when available
- one assistant-style natural memory sentence
- one primary action, usually `Open memory`
- a quiet attention marker only when human input is needed

Patient rows must not contain nested session cards, upload states, AI job states, or sync controls.

Example patient memory sentences:

- `Last visit focused on cheek volume and follow-up photos are saved.`
- `Recent notes mention Botox follow-up; memory is updated through today.`
- `Two recent visits are saved on this device and will be organized when online.`

## Needs Input Tab

Needs input is a human-decision inbox. It follows the shared [Needs input rules](../states.md#needs-input-rules).

Each item has calm explanatory wording and one clear primary action.

Example copy:

- `This visit is saved. Choose which patient it belongs to.`
- `I found two possible matches. Confirm the patient before I update memory.`
- `Summary is ready. Review before it becomes part of patient memory.`
- `Device storage is almost full. Please free space so new captures stay safe.`

## Patient Detail / Timeline

Opening a patient shows the long-term memory view for that patient.

The backend source is `GET /api/v1/patients/{patientId}/memory`. The main
patient-memory list stays flat; session timeline data belongs in this detail
response.

It includes:

- assistant-generated or assistant-style patient summary
- sessions grouped by time, such as `Today`, `Earlier this week`, `Earlier`
- each session summarized in human language
- one primary action per session, such as `Open visit`
- persistent capture context so the user understands where new captures will go

Timeline sessions may expose source captures and review details after the user opens them, but the Clinical Memory main view stays compact.

## Patient Card Summary Fallback Hierarchy

Patient cards should use the most natural available summary:

1. Assistant-generated patient memory sentence.
2. Rule-based natural summary from recent session summaries, visit dates, and capture types.
3. Metadata sentence, for example `Last updated today. 4 captures in the latest visit.`
4. Minimal saved-state sentence: `No memory summary yet.`

If AI output is unavailable, do not call that out as a failure. Use the next fallback.

## Screen-Specific Offline Behavior

Clinical Memory follows the shared [offline and AI-unavailable behavior](../states.md#offline-and-ai-unavailable-behavior).

Screen-specific behavior:

- Today and Patients continue to show locally saved memory.
- Today may show `Offline - Captures are saved on this device` and current-visit copy such as `3 captures saved on this device. I'll organize them when connection returns.`
- Search may be limited to patients saved on this device.
- Needs input still only shows human-decision or data-safety items.
- Do not show sync queues, retry buttons, backend job language, or AI failure language on Today.
