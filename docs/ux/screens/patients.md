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
- Tabs: `Today`, `Patients`, `Lists` (Pro only), `Needs input`. Basic shows three tabs — the Lists
  tab is simply absent (a legible upgrade, no teaser).
- Persistent bottom capture bar.

## Today Tab

Today is the default landing tab.

It shows:

- the `Today / up next` worklist (below), when relevant
- session/visit cards for active or recent work
- a compact `Needs your input` preview when human judgment is required
- calm saved-state language and capture chips such as `3 photos`, `1 audio`, `1 note`

### Today / up next (worklist)

A soft worklist card at the top of Today (AES-903; both tiers, deterministic). Reception
(assistant/admin) **creates** line-ups *for a doctor* — patient search, a doctor picker (doctors
only, never self), an optional note; a doctor **consumes** a read-only queue with a `Mine`/`Clinic`
scope toggle. Tapping a queued patient opens a recap popup — the tier-aware patient history plus the
prior visit's before/after — with **Start visit** (creates a session already assigned to that
patient and marks the entry seen) and `Open full timeline`. `Done` clears an entry; reception can
remove one. A pure consumer (doctor) with an empty queue sees no box at all, and the capture bar
always still starts a fresh session — a convenience lane, never a gate. No time slots; not a
scheduler. Backend: `worklist_entries` + `GET /api/v1/clinic/members`
([aes-basic-api §E9](../../backend/aes-basic-api.md)).

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
- exact needs-input label when relevant, such as `Needs input: verify patient`
- selecting the row opens patient history
- one focused action only when there is a current task, such as `Continue`, `Verify patient`, or `Assign patient`

Patient cards do **not** show an "active session" badge. Live/in-progress work belongs to the
[Today tab](#today-tab); the Patients list stays a calm long-term memory surface.

The needs-input label and its focused action are driven by the same backend-computed decision set
that powers the [Needs input tab](#needs-input-tab), so a patient's card badge and the tab always
agree. The three needs-input categories are: `assign patient` (unassigned visit), `choose patient`
(ambiguous/uncertain auto-match), and `verify patient` (an AI-created patient awaiting staff
confirmation). A processed, assigned visit with a current report needs no input.

Patient rows must not contain nested session cards, vague attention labels, upload states, AI job states, or sync controls.

When one patient has multiple needs-input decisions, the patient row primary action is `Review items`. This opens a patient-scoped drawer rather than the Active Session page. The drawer title is `{Patient name} needs your input`, the subtitle is `Review the decisions needed to keep this memory accurate.`, and the list includes only that patient's decision items. Each item shows the decision type, `Session:` time, reason, and a focused primary action such as `Choose patient` or `Verify patient`. `View patient history` may be offered as a secondary action.

Example patient memory sentences:

- `Last visit focused on cheek volume and follow-up photos are saved.`
- `Recent notes mention Botox follow-up; memory is updated through today.`
- `Two recent visits are saved on this device and will be organized when online.`

Example patient memory card:

- Patient: `Sara M.`
- Memory: `Last visit focused on cheek volume and follow-up photos are saved.`
- Latest visit: `Session: Apr 18 · 11:30 AM`
- Attention: `Needs input: verify patient`
- Row action: select row to view patient history
- Focused task action: `Verify patient`, when relevant

Avoid vague labels such as `Needs input` or `Review` when the card needs the user to act.

## Lists Tab (Pro)

One deterministic, zero-AI surface for two siblings built from the treatment data Pro synthesis
already extracts (`Session.extracted_metadata.treatments[]` + `Capture.metadata.photo_pairing`):
**smart lists** (AES-501, "who needs my attention?") and **lot/product recall** (AES-502, "who got
this batch?"). A small fixed set of lenses plus one lookup — never a configurable analytics
dashboard, and never a Basic teaser.

### Smart lists

A rail of named lenses with live counts. Each list is a deterministic predicate whose definition is
shown in the UI, so the count is trustworthy:

- **Seen this week** (patient-grained) — a visit in the last 7 days; newest first.
- **Due to return** (patient-grained) — most-recent visit ≥ 12 weeks ago, longest-overdue first,
  with the threshold shown (`Last seen 14 weeks ago`). There is no structured follow-up date in the
  data — the list is recency-based by design and never parses prose or invents a date.
- **Missing after-photo** (visit-grained) — a photo paired as `before` with no matching `after`
  (from the deterministic `photo_pairing`); tap opens the visit.

### Lot & product lookup + recall

One search box, two grains: browse by **product** ("on product X") or recall an exact **lot**. The
box is backed by the **lot ledger** — the distinct lots/products in the clinic's extracted data,
each with patient/visit counts — so staff pick from what was actually used instead of typing from
memory. Recalling a lot returns every patient who received it. Safety-grade rules:

- **Exact match only.** Normalization is uppercase + trim + collapse spaces; hyphens/dots are kept
  (`D-4471` ≠ `D4471`); never fuzzy. Near-misses surface in a separate **`Similar lots (not
  included)`** group — deliberate action only, never silently merged into the cohort.
- **Every row cites its source** — patient, visit date, the verbatim treatment line
  (area · product · units), and the extracted evidence snippet, linking to the visit.
- **A clear count summary** up top (`3 patients · 4 visits`); amber attention treatment, calm copy —
  a marker, never a blocker.
- **Outreach handoff** — per affected patient, **Open channel** opens (or reuses) their tokenized
  Q&A thread ([Q&A inbox](qa-inbox.md)) and yields a link to send; **Copy affected list** supports
  the clinic's own workflow. There is no bulk "Message all" (automated SMS/WhatsApp delivery is
  deferred, AES-404).

Backend: read-only, tenant-scoped, Pro-gated (`live_report_synthesis` capability → 403 on Basic) —
`GET /api/v1/smart-lists`, `GET /api/v1/smart-lists/{key}`, `GET /api/v1/lot-ledger`,
`GET /api/v1/lot-recall?lot=|?product=` (`app/services/smart_lists.py`). All lot/product reading is
aggregated in one ledger builder so the postponed AES-705 products/lots registry can layer on
(canonical lots, expiry, per-product due-to-return precision) without reshaping any response.

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
- Decision: `Verify AI-created patient`
  Session: `Session: Today · 4:23 PM`
  Patient: `Soroush`
  Why: `I created this patient from the visit. Confirm the details before it enters memory.`
  Primary action: `Verify patient` (opens the visit in Active Session, where the verify panel lives)
- Decision: `Storage warning`
  Since: `Needs input since: 2:20 PM`
  Why: `Device storage is almost full and new captures need room to stay safe.`
  Primary action: `Review storage`

Action routing:

- `Assign patient` opens an assign-patient sheet, modal, or page.
- `Choose patient` opens a patient-choice sheet, modal, or page (also used for a national-ID conflict).
- `Verify patient` opens the visit in Active Session, where the AI-created-patient verify panel completes/confirms the record.
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

Summary review resolver (available from a visit, **not** an unsolicited needs-input item):

- A processed, assigned visit no longer generates a "review summary" needs-input item — routine
  summary confirmation is not a critical decision. The resolver below is still reachable when a user
  opens a visit and chooses to review its drafted summary.
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

- a **patient history** brief at the top (see [Patient memory: summary and history](#patient-memory-summary-and-history))
- sessions grouped by actual session time: `Today`, `Earlier this week`, `Older`
- each session summarized in human language
- one primary action per session, such as `Open visit`
- persistent capture context, such as `Capturing for: Soroush · Today's visit`, so the user understands where new captures will go

Timeline cards label times explicitly. The session time is primary, for example `Session: Today · 4:23 PM`. Updated time appears only when it adds useful context, for example `Updated: 4:31 PM` or `Updated today · Patient assigned`. Needs-input cards name the exact decision, such as `Needs input: review summary`, `Needs input: choose patient`, or `Needs input: assign patient`.

## Patient Memory: Summary and History

Two patient-level memory artifacts are generated from the patient's visits and surfaced together:

- **Patient summary** — one to two sentences on the **patient card** (Patients tab).
- **Patient history** — a richer brief atop the **patient timeline/detail** page. Replaces the older single "Engram assistant summary:" line.

Both are tier-aware. The tone reads like a calm assistant in either tier; only the depth differs:

- **Pro** (`tenant.tier = pro`) is AI-maintained: a synthesized brief with titled prose sections — `Snapshot`, `Story so far`, `Worth remembering`, `Right now` — and a warm one-line card summary. A ✨ provenance mark accompanies these artifacts (and only these), pulsing while they refresh.
- **Basic** is deterministic and carries **no ✨**: a structural recap built from capture facts (visit counts, dates, capture types) plus any verbatim typed notes. It never paraphrases or guesses a topic from audio — Basic has transcription but no summarization, so audio visits read as e.g. `1 audio note (2m 14s). Transcript saved — open the visit to read it.`

Backend source: `GET /api/v1/patients/{patientId}/memory` returns `history` (`mode`, `status`, `snapshot`, `sections`, `visits`, `source`); the flat list and detail rows carry `summary` + `memoryStatus`.

Language: Pro AI copy is written in the tenant's report language (a future dedicated assistant-language axis is planned, separate from transcription/report). Names embedded in the copy are bidi-isolated so mixed-direction lines render cleanly; the UI also picks per-line direction so Persian/Arabic content reads RTL.

> **Pro** runs a real combined AI job (`patient_memory`): one model call produces the summary *and* history together (cheaper, mutually consistent), fed the prior memory plus compact per-visit briefs (incremental — not raw transcripts). It runs **only once the session is complete** — captures processed, a patient assigned (manually or auto-matched), and the report up to date — and is coalesced per patient. Model choice for this job (like every AI task) is managed centrally, not a user setting. If the gateway is unavailable, the job falls back to deterministic content so memory is never empty. **Basic** stays fully deterministic (no model call).

### Updating → ready state

A new capture (or an assignment change) marks the patient's memory `updating`; it returns to `ready` once the (mock) job settles. The surfaces never blank out:

- Existing summary/history stays legible while a soft shimmer sweeps the text, an `Organizing memory` cue shows, and the ✨ pulses (Pro).
- When it settles, the refreshed text fades in. Pro keeps the prior AI text visible during the refresh (never downgraded to the structural fallback); a patient with no memory yet shows the structural fallback first, then upgrades.
- Copy stays timeless and never exposes job/AI failure language, per [states](../states.md#assistant-state-language). A stale refresh never becomes a Needs-input item.

Timeline sessions may expose source captures and review details after the user opens them, but the Clinical Memory main view stays compact.

Selecting a timeline session opens the visit in Active Session. `Back` returns to the same patient timeline.

## Patient Card Summary Fallback Hierarchy

Patient cards should use the most natural available summary:

1. The persisted tier-aware [patient summary](#patient-memory-summary-and-history) (`memoryStatus`-tracked), once generated.
2. Rule-based natural summary from recent session summaries, visit dates, and capture types.
3. Metadata sentence, for example `Last updated today. 4 captures in the latest visit.`
4. Minimal saved-state sentence: `No memory summary yet.`

Before the first memory is generated (or if it is unavailable), fall through to the next item. Do not call that out as a failure.

## Screen-Specific Offline Behavior

Clinical Memory follows the shared [offline and AI-unavailable behavior](../states.md#offline-and-ai-unavailable-behavior).

Screen-specific behavior:

- Today and Patients continue to show locally saved memory.
- Today may show `Offline · Captures are saved on this device` and current-visit copy such as `3 captures saved on this device. I'll organize them when connection returns.`
- Search may show `You're offline. Patient search may be limited.`
- Needs input still only shows human-decision or data-safety items.
- Do not show sync queues, retry buttons, backend job language, or AI failure language on Today.
