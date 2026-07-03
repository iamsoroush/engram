# Active Session Workspace

## Route

- `/` — default staff screen after login (owners/doctors land here)
- `/#active-session`

## Purpose

The primary working screen: build and review a visit from audio, photo, and text captures.
Capture-first — nothing requires picking a patient or waiting for AI; captures save locally first
and everything else catches up. The same workspace structure renders historical visit review
opened from Clinical Memory or Search (read-only, with a Back action to where it came from).

**Vocabulary.** The aesthetics chrome noun for the clinical encounter is **visit** everywhere the
clinician reads it — the primary nav label, the `+ New visit` button, visit titles, and the `Visit:`
time label — even though the underlying data object (and code) is a `session`. Therapy keeps
`session`; the primary-nav label is chosen per vertical. Only chrome changes; clinical CONTENT is
untouched.

## Surface by tier

- **Basic** — the Clinical report card has a `Captures` / `Live report` tab switch. `Captures` is
  the chronological capture feed; `Live report` is a deterministic chronological document (clinic
  header + patient block from template/DB, transcripts and photos with honest timestamps) rebuilt
  in place as captures land. No AI synthesis, no verify bar, no safety panel; the header is
  lightweight (no `Complete` badge).
- **Pro** — a unified, report-first surface with no tabs: the synthesized report is the primary
  surface and the raw captures are demoted to a collapsible **Sources** drawer beneath it.
  Top-to-bottom: AI usage notice → sticky verify bar → patient card → safety panel → session
  context card → verify region → report card (with aftercare, feedback bar, and the Sources drawer
  inside it).

## Capture actions

- Sticky bottom bar on every staff screen: `Audio` (`Tap to record`), `Take photo`, `Write note`.
  From Clinical Memory or Search the bar first shows a compact **destination chooser**
  (current/recent sessions or a new session).
- **Audio** opens a bottom sheet with timer, animated levels, pause/resume, stop/save, discard,
  background-continue, and a `Use audio file instead` fallback. A single recording **auto-stops
  and saves at 20 minutes** (fair-use cap — a mic left open cannot burn the monthly AI budget in
  one clip). A low-durable-storage warning guards before long recordings.
- **Take photo** opens a bottom sheet with camera and device-library options, a large preview,
  save actions disabled until a photo is selected, and security copy. Empty selections are
  rejected before save/upload.
- **Write note** opens a note sheet.
- Every capture is written to IndexedDB first and appears immediately; upload, processing, and
  report updates follow. See the [capture-session workflow](../workflows/capture-session.md).
- Visit header: a meaningful title (the patient's Nth visit, or date/time), status chip,
  capture count, and `+ New visit` (shown once the active visit has captures). A visit
  started by another staff member opens **read-only** with a banner naming who started it.
- A calm, non-blocking **AI usage notice** (`AiUsageNotice`) renders above the workspace when the
  clinic is approaching or at its monthly AI budget — captures are always still saved. See
  [states](../states.md) and `docs/business/ai-usage-limits.md`.

## Patient assignment

- A **patient card** always renders: avatar, assigned patient name + assignment source
  (`Matched by AI`, manual, voice-reassigned), or capture-first copy when unassigned (soft amber
  attention state, never an error). Actions: `Assign`/`Change` (opens the assignment bottom sheet
  with suggested matches, search, and inline patient creation) and `History` (patient timeline).
- If audio transcription extracts a patient identity, a **deterministic** existing match assigns
  the visit with AI provenance; if nothing matches and the identity is usable, the backend creates
  and assigns an AI-origin patient. Assignment is stored as a timeline: the latest valid action
  wins, deleted-capture actions are skipped, and later manual assignment blocks older AI actions.
- An **AI-created patient** shows an inline completion/verification panel (name, national ID,
  phone, date of birth) in the verify region — staff never leave the session to verify it.
- A "next lined-up patient" hint offers `Assign this visit` / `Start their visit` when the session
  is unassigned and a patient is waiting.

### Partial-match resolution (the decision matrix)

Apply semantics live in [intelligence-layer §5](../../intelligence-layer.md); this is the surface.
The backbone is **basis** (explicit | implicit) × **match quality** (exact | partial | none) ×
**visit state** (unassigned | already-assigned):

| match quality | visit state | basis = explicit | basis = implicit |
| --- | --- | --- | --- |
| **exact** (deterministic) | unassigned | assign | assign (first-identity-wins) |
| **exact** | assigned | reassign (override) | **Suggested: reassign** (not applied) |
| **partial** (fuzzy) | unassigned | **Suggested** → quick actions; **auto-applies** only under `balanced`/`lenient` strictness + a single high-confidence candidate | **Suggested** (no auto-apply) |
| **partial** | assigned | **Suggested** → quick actions; **auto-applies** only under `balanced`/`lenient` strictness + a single high-confidence candidate | **Suggested** (no auto-apply) |
| **none** (usable identity) | unassigned | create + assign, flagged **verify** (editable) | create + assign, flagged **verify** |
| **none** | assigned | create + assign (override), flagged **verify** | quiet (a bare mention; no chip unless a candidate surfaces) |

Invariants at **every** strictness: a partial match is **never silently applied**; the national-ID
**conflict guard** routes to review; multiple comparable candidates route to the choose-patient
resolver, never auto-apply.

On a partial match the resolver shows **what was matched vs what was spoken** ("Matched *معاصد* ·
you said *معاضد*") with one-tap actions:

- **Keep match** — assign the visit to the matched patient (attributed to this capture; reversible).
- **Create new patient instead** — an inline new-patient form prefilled from the *spoken* identity,
  editable → create + assign, flagged **verify**. This is also the edit surface; a matched
  **existing** record is never silently renamed from a fuzzy capture.
- **Choose another** — the assignment resolver (search / detected-in-session / create).

A dictated different/partial-match patient is a **session-level blocker**: the resolver
(`PatientConflictResolver`) renders in the verify region as a "Patient needs your confirmation"
panel and is counted by the verify bar; the same resolver also renders on the originating capture
in the Sources drawer. When strictness auto-applies a close match it is reversible: the capture
shows the applied chip with a `· close match` note, the matched-vs-spoken line, and **Undo**. The
per-tenant **match strictness** setting (Strict / Balanced / Lenient) lives on the
[Settings page](account.md).

## Session context card

When the session's patient becomes known — manual assign or AI match — a deterministic
**session context card** (`SessionContextCard`, both tiers, zero AI) renders between the safety
panel and the verify region. It answers, glanceably: who this is (visit ordinal, pinned key
facts), what happened last (the full **last-visit digest** — notes, photo thumbnails, playable
voice memos, `Same as last time` pre-fill), and progress (a compact **cross-visit photo strip**;
tapping a thumb opens a before/after compare overlay). The patient's kept **safety flags** surface
here at every future visit. It hides for a brand-new patient with nothing to show, and clears when
the patient is removed or reassigned.

- **Pro** layers the AI patient-memory **lineup card** (story-so-far, since-last delta, hero
  photo) on top of the deterministic base — so Pro is never blank when AI is unavailable.
- **Timeline round-trip:** `View full history` opens the patient timeline, which shows a
  persistent **`Back to this visit`** that restores the in-progress session exactly — the
  clinician can glance at history mid-capture and return in one tap.
- **Auto-collapse:** the card is a *pre-capture* glance aid, so once the report has content it
  **auto-collapses** to a single tappable line (visit ordinal + a `Show visit context` nudge; a
  safety chip stays if flags are on record). A tap re-expands it and a chevron re-collapses it;
  undoing every capture re-expands it. It is fully open before any captures exist.
- Backend: `GET /api/v1/patients/{id}/session-context`.

## Pro report surface

### Verify bar and verify region

- A sticky **"N to confirm"** verify bar counts **blockers only** — unconfirmed carried-forward
  doses and AI-created-patient identity (plus patient conflicts). `Review` jumps to the first
  inline confirm. Soft warnings never feed it ("warnings over blocking"). While synthesis is still
  in flight with no blockers yet it shows a quiet `Checks pending · organizing` state (calm blue,
  no action); it renders **nothing** only once the report has settled clean — so an empty bar means
  the checks ran, never "not yet checked".
- The **verify region** above the report holds the patient-conflict resolver panels and the
  AI-created-patient verification panel. Everything else confirms **inline where the data is**: a
  carried-forward dose shows `Confirm dose` directly on its treatment row and flips to
  `✓ Dose confirmed` in place; softer uncertainties render as calm gray footnotes beneath the
  treatments list.

### Safety panel

The synthesis detects clinical **safety flags** from the captures — allergy / contraindication /
consent statements the clinician actually made — and surfaces them in a calm red/amber panel
**above** the verify region (safety is highest priority). Flags are **opt-out**: every detected
flag is shown and kept by default; the clinician acts only to reject (×) a wrong one. The panel is
**not** a verify-bar blocker and never gates the report. A rejection persists (survives
re-synthesis) and is logged as an AI-feedback signal. Non-rejected flags project onto the patient
and resurface cross-visit in the session context card and the patient timeline. The flag body is
clinical content in the report language and is never translated — only the chrome is bilingual.
Endpoint: `POST /api/v1/sessions/{id}/safety-flag-rejection`.

### Report card

- Header: `Clinical report` with an **AI spark** provenance mark (it twinkles while a synthesis is
  in flight), a quiet updating spinner, and a compact **Share** affordance (Pro, assigned visit
  with captures) that opens the curate + preview clinic→patient share sheet — see
  [session review](session-review.md).
- The report is synthesized by a background AI job over a deterministic baseline; it is **never
  blank while updating**. Adding a capture keeps the prior report visible with an explicit
  freshness line — `✓ Reflects all N captures` when current, `Updating · N of M captures not yet
  in this report` plus a shimmer while a synthesis runs. The held report is swapped only when a
  fresh synthesis arrives. See [states — Organizing](../states.md).
- Section titles follow the **report language** (Persian titles for a Persian report); body text
  direction is per-line (RTL for Persian/Arabic content).
- **Per-claim source citations:** report blocks and treatment rows carry a small `↗ source` tap
  that opens the cited capture.
- **Fix at source:** soft extraction gaps (low confidence, missing lot) render as quiet inline
  flags on the treatment row with a `Fix at source` deep-link that opens the originating capture in
  the Sources drawer — correct the capture text and the AI re-extracts. There is **no direct
  treatment-field edit**.
- **Aftercare:** content-driven aftercare templates are AI-matched and auto-included (opt-out) —
  each shows with a remove (✕); dismissals persist across re-synthesis. When dictated aftercare
  contradicts a protocol, the dictation wins and a conflict note is shown instead of the template.
- A quiet **report feedback bar** (thumbs rating, eval golden-set harvester) ends the report.

### Sources drawer and undo

- The raw captures live in a collapsible **`Sources · N`** drawer beneath the report: count badge,
  per-type chips (audio/photo/note), and a calm `Organizing…` pulse while captures are still being
  processed (hidden once done). It auto-expands while the report is still empty. All capture
  edit/delete/reassign/open affordances live here.
- **Undo last capture** sits in the drawer header — one tap removes the most recent capture
  without expanding the drawer. Undo and the per-capture **Delete** are the same **de-effecting
  removal**: reverting a capture reverts *its effects* — the patient it created or assigned (a
  spurious AI-created patient with no other dependents is soft-deleted; otherwise the visit is
  unassigned), its treatments, its safety flags, and its report contribution. Removing the latest
  capture **restores** the exact prior report version deterministically (no LLM, no new wrong
  entries); removing a middle capture triggers a recompute shown as a calm re-organizing state.
  Removal is **owner-only** (the staff member who started the session). Architecture:
  [pipeline-versioning](../../architecture/pipeline-versioning.md).

## Capture cards (feed / Sources drawer)

- Audio renders inline playback; transcripts and photo captions render fully inline (no detail
  card needed for review) and their headings show whether the text is **AI-generated or
  staff-edited**. Notes show decorated text plus an expandable raw-note section.
- In-progress chips use only `Syncing`, `Uploading`, or `Processing`; type-specific working copy
  (`Transcribing audio`, `Reading image`) lives inside the generated-text area. Completed captures
  show no technical status.
- The active assignment-source capture shows `Patient assigned` / `Patient created` badges; older
  AI source captures lose the badge when a later action supersedes them.
- Per-capture overflow: rename, delete (the de-effecting removal above).
- Tapping a capture opens a source preview sheet: media preview, metadata, editable
  transcript/caption with edit attribution, and a copy control.

## States

Shared rules: [states](../states.md).

- **Loading:** source previews use the local cache first, then protected backend file content.
- **Empty:** no captures still shows the workspace with an empty report surface and
  capture-first guidance.
- **Offline:** calm reassurance (`Offline · Captures are saved on this device`); capture continues.
- **Errors:** toasts for storage, audio conversion, save, and user-action failures; critical
  local-save/storage issues warn because data safety is at risk.
- **Success:** by exception — a clean visit shows no nag; completeness reads from the `Complete`
  badge and the freshness line.

## Main Components

- `Shell`, `CaptureActions`, `CaptureScreen`
- `SessionVerifyBar`, `PatientConflictResolver` + `AiCreatedPatientPanel` (CaptureBadges)
- `SessionContextCard` (+ `LineupCard`), the `session-safety-panel`
- `LiveReportView` + `TreatmentsList`, the `sources-drawer`, `ReportFeedbackBar`
- `AiUsageNotice`
- `AudioDialog`, `AddPhotoSheet`, `TextCaptureSheet` (CaptureDialogs), `SourcePreviewDialog`,
  `PatientAssignmentSheet`

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Clinical Memory workflow](../workflows/review-and-assign-patients.md)

## Related APIs

- `POST /api/v1/captures` · `GET /api/v1/sessions/{id}/captures` ·
  `GET /api/v1/captures/{id}/file-content`
- `PATCH /api/v1/captures/{id}` (rename, edit transcript/caption) ·
  `DELETE /api/v1/captures/{id}` (de-effecting removal / undo)
- `POST /api/v1/sessions/{id}/save` (auto-invoked via the outbox as captures sync)
- `POST /api/v1/sessions/{id}/assign-patient` · `GET /api/v1/sessions/{id}/assignment-suggestion` ·
  `PATCH /api/v1/sessions/{id}` (rename, AI-created-patient verification)
- `POST /api/v1/sessions/{id}/safety-flag-rejection` ·
  `POST /api/v1/sessions/{id}/confirm-carried-forward` ·
  `POST /api/v1/sessions/{id}/aftercare-dismissal`
- `GET /api/v1/patients/{id}/session-context` · `GET /api/v1/patients/search` ·
  `POST /api/v1/patients`
- `GET /api/v1/ai-usage`

## Known Gaps

- `+ New visit` resets the active context locally; the remote session is created when the first
  capture syncs (a pre-assigned patient is attached then).
- Historical review shares the report workspace but does not expose the full patient assignment
  panel.
