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

- current visit or current capture destination
- a small `Needs your input` preview when human judgment is required
- recent memory updates
- calm saved-state language

It does not show all patients or all sessions.

Example copy:

- `Memory updated for Sara M.`
- `Saved. Organizing the visit notes.`
- `1 visit needs your input.`
- `No urgent input needed. Keep capturing when ready.`

## Patients Tab

Patients is a searchable, scalable list of patient memory.

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
3. Metadata sentence, for example `Last saved visit: May 27. Photos and note are saved.`
4. Minimal saved-state sentence, for example `Patient memory is saved.`

If AI output is unavailable, do not call that out as a failure. Use the next fallback.

## Screen-Specific Offline Behavior

Clinical Memory follows the shared [offline and AI-unavailable behavior](../states.md#offline-and-ai-unavailable-behavior).

Screen-specific behavior:

- Today and Patients continue to show locally saved memory.
- Search may be limited to patients saved on this device.
- Needs input still only shows human-decision or data-safety items.
