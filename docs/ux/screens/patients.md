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

- session/visit cards for active or recent work
- a compact `Needs your input` preview when human judgment is required
- calm saved-state language and capture chips such as `3 photos`, `1 audio`, `1 note`

Today is session-first. A card may include patient context, but the primary object is the session or visit, not the patient. Do not show generic patient cards that hide the session identity.

Today includes only sessions created, captured, or updated on the user's current calendar day. Older unassigned or historical sessions belong in Patients, Search, or the full Needs input surface, not in the Today preview.

The current visit card uses natural assistant copy. If the visit has a patient, show the patient name as context; otherwise show `Unassigned visit`. Selecting a Today card opens that visit in Active Session, where `Back` returns to Today. Use a visible action only for the focused next task, such as `Continue visit`, `Assign patient`, or `Review summary`; do not show a separate `Open visit` action.

Every Today card must clarify why it appears in Today with section or badge language such as `Active session`, `Needs your input`, `Updated today`, `Recently captured`, or `Saved on this device`. Session time and update/attention time must be labeled separately.

Choosing `Assign patient` from Today opens the same patient assignment form in Clinical Memory without navigating away from the tab. Suggested matches come from patient search data; do not use mock patient suggestions in production UI.

Example active session card:

- Title: `Follow-up visit`
- Patient: `Soroush`
- Session: `Today · 4:23 PM`
- Updated: `4:31 PM`
- Summary: `4 captures saved: 3 photos and 1 audio note. I'm preparing the visit summary.`
- Capture chips: `3 photos`, `1 audio`, `1 note`
- Badge: `In progress`
- Primary action: `Continue visit`

Example needs-input preview card:

- Title: `Unassigned visit`
- Session: `Today · 2:15 PM`
- Needs input since: `2:20 PM`
- Summary: `3 captures saved. I could not confidently attach this visit to a patient.`
- Primary action: `Assign patient`
- Card selection: opens the visit in Active Session

Example updated-today card:

- Title: `Initial consultation`
- Patient: `Sara`
- Session: `Apr 18 · 11:30 AM`
- Status: `Updated today · Patient assigned`
- Summary: `2 photos and 1 note were attached to this visit today.`
- Card selection: opens the visit in Active Session

Example copy:

- `Memory updated for Sara M.`
- `Saved. Organizing the visit notes.`
- `1 visit needs your input.`
- `No active visit. Start with audio, photo, or note.`
- `All caught up.`
- `Recent patients will appear here.`

## Patients Tab

Patients is a searchable, scalable list of patient memory. It is patient-memory-first, not a session inbox.

The backend source for this list is `GET /api/v1/patient-memory`. The endpoint
returns flat patient-memory rows with summary fallbacks, latest-session metadata,
session counts, active-session markers, and pagination. The frontend should not
derive this tab by loading every session and grouping client-side.

Each patient row/card includes:

- patient name and compact identifying context when available
- one assistant-style natural memory sentence
- latest visit reference when useful
- active session badge when a patient has an active visit
- exact needs-input label when relevant, such as `Needs input: review summary`
- selecting the row opens patient history
- one focused action only when there is a current task, such as `Continue`, `Review summary`, or `Assign patient`

Patient rows must not contain nested session cards, vague attention labels, upload states, AI job states, or sync controls.

When one patient has multiple needs-input decisions, the patient row primary action is `Review items`. This opens a patient-scoped drawer rather than the Active Session page. The drawer title is `{Patient name} needs your input`, the subtitle is `Review the decisions needed to keep this memory accurate.`, and the list includes only that patient's decision items. Each item shows the decision type, `Session:` time, reason, and a focused primary action such as `Review summary` or `Choose patient`. `View patient history` may be offered as a secondary action.

Example patient memory sentences:

- `Last visit focused on cheek volume and follow-up photos are saved.`
- `Recent notes mention Botox follow-up; memory is updated through today.`
- `Two recent visits are saved on this device and will be organized when online.`

Example patient memory card:

- Patient: `Sara M.`
- Memory: `Last visit focused on cheek volume and follow-up photos are saved.`
- Latest visit: `Session: Apr 18 · 11:30 AM`
- Badge: `Active session`
- Attention: `Needs input: review summary`
- Row action: select row to view patient history
- Focused task action: `Continue`, when relevant

Avoid vague labels such as `Needs input` or `Review` when the card needs the user to act.

## Needs Input Tab

Needs input is a decision-first human-decision inbox. It is not a technical error queue and not a session list. It follows the shared [Needs input rules](../states.md#needs-input-rules).

Each card must answer:

- what decision is needed
- which session or visit is involved
- which patient is involved, if known
- why user input is needed
- the smallest focused action that resolves it

The primary action must open a focused resolver, not simply redirect to the active session page. Selecting the card itself opens the visit in Active Session, where `Back` returns to Needs input, so Needs input cards do not show a separate `Open visit` action.

Example copy:

- Decision: `Unassigned visit`
  Session: `Session: Today · 4:23 PM`
  Patient: `Unknown`
  Why: `This visit is saved, but I do not know which patient it belongs to.`
  Primary action: `Assign patient`
  Card selection: opens the visit in Active Session
- Decision: `Patient match uncertain`
  Session: `Session: Apr 18 · 11:30 AM`
  Patient: `Possible matches: Sara M., Sarah Mahmoud`
  Why: `I found two possible matches before updating memory.`
  Primary action: `Choose patient`
- Decision: `Patient match found`
  Session: `Session: Today · 4:23 PM`
  Patient: `Likely match: Sara Nazari`
  Why: `The visit mentions identity details that match an existing patient. Confirm before I update memory.`
  Primary action: `Choose patient`
- Decision: `Summary ready for confirmation`
  Session: `Session: Today · 4:23 PM`
  Patient: `Soroush`
  Why: `Review before it becomes part of patient memory.`
  Primary action: `Review summary`
- Decision: `Storage warning`
  Since: `Needs input since: 2:20 PM`
  Why: `Device storage is almost full and new captures need room to stay safe.`
  Primary action: `Review storage`

Action routing:

- `Assign patient` opens an assign-patient sheet, modal, or page.
- `Choose patient` opens a patient-choice sheet, modal, or page.
- `Review summary` opens the summary review flow.
- `Review storage` opens the storage guidance or review flow.

Assign-patient resolver:

- Title: `Assign patient`.
- Show compact visit context: `Unassigned visit`, `Session: ...`, capture counts, and a short summary when available.
- Show suggested patient rows when patient search data is available, with avatar/initials, name, hint, and selection state.
- Include `Search patient`, `Create new patient`, `Keep unassigned`, and secondary `Open visit`.
- Selecting a patient reveals a clear confirmation action such as `Assign to Soroush`.
- On success, close the resolver, update Clinical Memory state, and show subtle copy such as `Visit assigned to Soroush`.

Choose-patient resolver:

- Title: `Choose patient`.
- Explain that the visit may belong to more than one patient and the user should choose the correct patient.
- Show compact session context, capture counts, and a short human-readable hint when available.
- Show candidate patient cards with initials, name, reason/hint, confidence, risks when present, and selected state.
- Candidate rows may come from backend `patient_match_candidate` metadata. The resolver must still require staff confirmation; suggested matches never assign, create, merge, or rewrite patient names automatically.
- Include `Search another patient`, `Create new patient`, and `Keep unassigned`.
- Confirm with `Confirm patient`.
- On success, close the resolver, remove the needs-input item from Clinical Memory, update related session/patient cards, and show `Patient confirmed`.

Summary review resolver:

- Title: `Review summary`.
- Show compact context: patient, session time, and capture counts.
- Show the drafted visit summary in readable form, with compact source chips such as `3 photos`, `1 audio`, and `1 note`.
- Include primary `Confirm summary`, secondary `Edit summary`, and secondary `Open visit`.
- Editing stays inside the focused resolver when supported.
- On success, close the resolver, remove the needs-input item, update the patient memory sentence, and show `Summary added to patient memory`.

## Patient Detail / Timeline

Opening a patient shows the long-term memory view for that patient.

The backend source is `GET /api/v1/patients/{patientId}/memory`. The main
patient-memory list stays flat; session timeline data belongs in this detail
response.

It includes:

- assistant-generated or assistant-style patient summary
- sessions grouped by actual session time: `Today`, `Earlier this week`, `Older`
- each session summarized in human language
- one primary action per session, such as `Open visit`
- persistent capture context, such as `Capturing for: Soroush · Today's visit`, so the user understands where new captures will go

Timeline cards label times explicitly. The session time is primary, for example `Session: Today · 4:23 PM`. Updated time appears only when it adds useful context, for example `Updated: 4:31 PM` or `Updated today · Patient assigned`. Needs-input cards name the exact decision, such as `Needs input: review summary`, `Needs input: choose patient`, or `Needs input: assign patient`.

Timeline sessions may expose source captures and review details after the user opens them, but the Clinical Memory main view stays compact.

Selecting a timeline session opens the visit in Active Session. `Back` returns to the same patient timeline.

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
- Today may show `Offline · Captures are saved on this device` and current-visit copy such as `3 captures saved on this device. I'll organize them when connection returns.`
- Search may show `You're offline. Patient search may be limited.`
- Needs input still only shows human-decision or data-safety items.
- Do not show sync queues, retry buttons, backend job language, or AI failure language on Today.
