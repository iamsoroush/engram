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
  surface and the raw captures are demoted to a collapsible **Sources** drawer beneath it. The chrome
  above the report is deliberately thin (the **layout diet**), top-to-bottom: a thin AI-usage bar
  (only near/at budget) → the one-line **patient strip** (identity + context + verify chip + safety
  chip — see "Patient strip") → a thin conflict band only while a patient conflict is active → report
  card (with aftercare, feedback bar, and the Sources drawer inside it). Everything the strip absorbs
  is one tap away in its expansion.

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

- Identity always renders in the **patient strip** (below): avatar, assigned patient name +
  assignment source (`Matched by AI`, manual, voice-reassigned), or a soft-amber `Unassigned`
  attention state (never an error) that keeps `Assign` prominent even collapsed. Actions live in the
  strip's expansion: `Assign`/`Change` (opens the assignment bottom sheet with suggested matches,
  search, and inline patient creation) and `History` (patient timeline). (Historical review keeps a
  flat patient card instead of the strip — no pending actions to diet away.)
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
| **none** | assigned | reassign, or **rename in place** (Fix 1) when the current patient is an AI-created *unverified* record and the correction is explicit; else **Correct name to X?** | **Correct name to X?** suggestion when the spoken name differs from the assigned patient; otherwise quiet (a genuine echo) |

Invariants at **every** strictness (all enforced by the never-silent completion assertion, INV-SILENT):
a partial match is **never silently applied**; the national-ID **conflict guard** (incl. the A-F5
spoken-name cross-check) routes to review; multiple comparable candidates route to the choose-patient
resolver, never auto-apply. A **dead-zone near-miss** on an unassigned visit (below the 0.78 suggest
floor) creates + assigns the spoken patient and keeps the look-alike as a *"similar to existing Y"*
note (Fix 7). An **out-of-context** capture never files/creates a patient — its identity is downgraded
to a suggestion (A-F4).

Added chip kinds (E1) beyond reassign/create — each a visible, never-silent surface with **one-tap
apply** on the resolver (Track B):

- **Correct name to X?** (`suggested_name_correction`) — one tap renames the assigned patient **in
  place** (`POST /sessions/{id}/apply-name-correction`; an unverified AI record renames freely, a
  verified chart needs the owner-class preset). No re-synthesis.
- **Unassign this visit?** (`suggested_unassign`) — from a detach/negation capture ("wrong patient,
  remove her"); one tap clears the patient via the assignment choke point
  (`POST /sessions/{id}/unassign-patient`), consuming the capture's suggestion.
- **Couldn't apply — assign manually** (`assignment_no_effect`) — an explicit instruction that matched/created nothing.
- **similar-to-existing** note on a dead-zone create; **conflict** chip for a recovered-but-inert assignment.

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

## Patient strip

The **patient strip** (`PatientStrip`, both tiers, active sessions) is the sticky one-line surface
above the report that absorbs identity + session context + verify state + safety — the **layout
diet** (nine stacked zones → strip → report). Two states:

- **Collapsed (one line):** avatar · patient name · visit ordinal · assignment state (`✓ assigned` /
  `Matched by AI` / soft-amber `Unassigned · Assign`) · an amber `⚠ N to confirm` chip (the blocker
  count) · a red `🩹` safety chip when flags are on record · a chevron. Tapping a chip expands the
  strip; the chevron toggles it. It stays **sticky** while scrolling a long report, so identity +
  safety + count are always visible.
- **Expanded:** patient actions (`Assign`/`Change`, `History`) · the full safety panel · the session
  context digest · the AI-created-patient verify panel.

**Auto-collapse state machine:** pre-capture the strip is **expanded** (a glance aid before you
capture); once the **report has content** it **collapses** to one line; **undoing every capture**
re-expands it; historical review is collapsed. An **unassigned** visit stays collapsed but keeps
`Assign` prominent. **Manual override always wins** (a tap expands, the chevron collapses).
**History auto-surfaces:** when a patient **with history** is assigned or reassigned, the strip
auto-expands to that history — collapse waits until the report has content **and** the history has
been surfaced (a new assignment event re-surfaces it).

- **Basic** gets a simpler strip (identity + context, no verify/safety chips — those are Pro).
- **Never bury safety:** a red safety chip is always shown collapsed; the tenant **high-risk-clinic**
  setting ([Settings](account.md)) pins the *full* safety panel open above the report — never a chip.
- **Conflicts are never buried:** an active patient conflict keeps a **thin, always-visible band**
  above the report (resolvable in place); the strip expansion is a second entry point.

## Session context card

When the session's patient becomes known — manual assign or AI match — a deterministic
**session context card** (`SessionContextCard`, both tiers, zero AI) renders **inside the patient
strip's expansion**. It answers, glanceably: who this is (visit ordinal, pinned key
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
- **Collapse** is driven by the enclosing patient strip's state machine (above), not its own.
- Backend: `GET /api/v1/patients/{id}/session-context`.

## Pro report surface

### Verify chip and resolvers

- The strip's **`⚠ N to confirm`** chip counts **blockers only** — unconfirmed carried-forward doses
  (that have a rendered row), AI-created-patient identity, and patient conflicts. Soft warnings never
  feed it ("warnings over blocking"); it hides once the report settles clean. **Every counted blocker
  has a reachable resolver** (a tested invariant): tapping the chip expands the strip and scrolls to
  the topmost — the conflict band, the AI-created-patient panel in the strip, or the inline dose row.
- **Patient conflicts** render in a **thin, always-visible band** above the report (the
  `PatientConflictResolver`), resolvable in place — a name-correction / unassign applies in one tap,
  or Keep-match / Create-new / Choose-another / Assign-manually. The **AI-created-patient** verify
  panel lives in the strip expansion. Everything else confirms **inline where the data is**: a
  carried-forward dose shows `Confirm dose` on its treatment row and flips to `✓ Dose confirmed` in
  place (or is auto-satisfied by a dose edit — see the treatment overlay); coded uncertainties render
  as calm notes beneath the treatments list (actionable — fix-at-source / open-source — where coded).

### Safety panel

The synthesis detects clinical **safety flags** from the captures — allergy / contraindication /
consent statements the clinician actually made — and surfaces them in a calm red/amber panel. It
lives in the **patient strip** — always represented by the strip's red safety chip when collapsed,
the full flag list in the expansion — **unless** the tenant is a **high-risk clinic**
([Settings](account.md)), where the full panel is **pinned open above the report** and never collapses
to a chip. Flags are **opt-out**: every detected flag is shown and kept by default; the clinician acts
only to reject (×) a wrong one. The panel is **not** a blocker and never gates the report. A rejection
persists (survives re-synthesis) and is logged as an AI-feedback signal. Non-rejected flags project
onto the patient and resurface cross-visit in the session context card and the patient timeline. The
flag body is clinical content in the report language and is never translated — only the chrome is
bilingual. Endpoint: `POST /api/v1/sessions/{id}/safety-flag-rejection`.

### Report card

- Header: `Clinical report` with an **AI spark** provenance mark (it twinkles while a synthesis is
  in flight), a quiet updating spinner, a compact **Share** affordance (Pro, assigned visit
  with captures) that opens the curate + preview clinic→patient share sheet — see
  [session review](session-review.md) — and a quiet **History** affordance (Pro, any visit with
  captures) that opens the **report version timeline** (see *Report history* below).
- The report is synthesized by a background AI job over a deterministic baseline; it is **never
  blank while updating**. Adding a capture keeps the prior report visible with an explicit
  freshness line — `✓ Reflects all N captures` when current, `Updating · N of M captures not yet
  in this report` plus a shimmer while a synthesis runs. The held report is swapped only when a
  fresh synthesis arrives. See [states — Organizing](../states.md).
- Section titles follow the **report language** (Persian titles for a Persian report); body text
  direction is per-line (RTL for Persian/Arabic content).
- **Per-claim source citations:** report blocks and treatment rows carry a small `↗ source` tap
  that opens the cited capture.
- **Direct treatment-field edit (Pro, AES-1102).** Each treatment row carries a quiet **✎** that
  opens a compact per-field editor (`area · product · brand · quantity · lot`); a change saves
  **instantly** as a user-owned overlay — no re-synthesis, no AI budget — and is authoritative on
  render (synthesis can never silently overwrite it). An edited field flips to an `✎ Edited by you`
  chip with a provenance subline that keeps the AI/dictated value visible (`AI Dose: ۲۰ واحد`) and a
  one-tap **Use AI** (revert); editing a carried-forward dose auto-satisfies its `Confirm dose`
  blocker (Q4); a human-confirmed field clears its low-confidence/missing-lot chip; a re-key/removed
  edit parks as an **orphan chip** (never lost). Full spec: [session review](session-review.md).
- **Correcting a treatment row** is the inline ✎ **Edit** (a durable, instant human overlay — never a
  re-synthesis), plus the `↗ source` citation for traceability. The row itself carries **no** separate
  "Fix at source" button (it duplicated the overlay path and contradicted the overlay decision).
  `Fix at source` survives only on a **coded review note that has no editable row** (a soft gap —
  low confidence / missing lot — surfaced beneath the list), where it deep-links to the capture so the
  AI re-extracts. Action chips (source, edit) are chrome and follow the **app** language, not the
  report language.
- **Planned vs performed treatments.** The synthesis classifies each treatment by tense/intent. A
  **performed** treatment renders in the `Treatment performed` table (an **uncertain** one stays there
  with low-confidence styling); a **planned** treatment (future-tense / stated intent — «دفعه بعد لب رو
  با ژل انجام می‌دیم») renders instead as a calm `Planned` line under **Plan & follow-up**, never as
  performed. So a future-tense dictation no longer lands under "Treatment performed" with a heavy review
  note; it is recorded as the plan it is (and never counts toward recall/lot cohorts/insights/memory).
- **Aftercare:** content-driven aftercare templates are AI-matched and auto-included (opt-out) —
  each shows with a remove (✕); dismissals persist across re-synthesis. When dictated aftercare
  contradicts a protocol, the dictation wins and a **conflict note** is shown (itself dismissable ✕,
  writing `dismissed_aftercare`) instead of the template.
- A quiet **report feedback bar** (thumbs rating, eval golden-set harvester) ends the report.

### Sources drawer and undo

- The raw captures live in a collapsible **`Sources · N`** drawer beneath the report: count badge,
  per-type chips (audio/photo/note), and a calm `Organizing…` pulse while captures are still being
  processed (hidden once done). It auto-expands while the report is still empty. All capture
  edit/delete/reassign/open affordances live here. Each card plays/edits inline (audio has a compact
  player; transcript/caption tap-to-edit); tapping an **audio** card's body opens its full detail
  (larger player + transcript + metadata) — the player controls and inline editors keep their own taps.
- **Undo last capture** sits in the drawer header — one tap removes the most recent capture
  without expanding the drawer. Undo and the per-capture **Delete** are the same **de-effecting
  removal**: reverting a capture reverts *its effects* — the patient it created or assigned (a
  spurious AI-created patient with no other dependents is soft-deleted; otherwise the visit is
  unassigned), its treatments, its safety flags, and its report contribution. Removing the latest
  capture **restores** the exact prior report version deterministically (no LLM, no new wrong
  entries); removing a middle capture triggers a recompute shown as a calm re-organizing state.
  Removal is **owner-only** (the staff member who started the session). **Undo last capture** is also
  the one-tap shortcut for *restore the previous version* (N=1) surfaced richer in *Report history*
  below. Architecture: [pipeline-versioning](../../architecture/pipeline-versioning.md).

### Report history (E14 · Pro)

The report-card header's quiet **History** affordance opens the **version timeline** — one entry per
stored synthesis (`session_report_versions`), newest-first: a **trigger label** derived from the
capture-set delta (photo added / transcript edited / capture removed / first report / …), capture count,
and demoted provenance (`AI-generated`). The current version is tagged `Current`. It is the navigable
face of the version store capture-undo already uses; Pro only (Basic has no synthesis chain). Trigger
labels are **chrome** (localized fa/en from a structured `{kind, count?}` the backend sends — never a
server-authored string).

- **Preview (read-only).** Tapping a version renders that report **read-only inside the sheet** — the
  same report presentation — with a `Viewing the version from HH:MM · Back to current` banner. The live
  **user-state overlay** (rejected safety flags, dismissed aftercare, confirmed doses, treatment edits)
  applies on top of whichever version renders, so a user decision is **never time-traveled away**.
- **Restore (owner-only).** A past version reachable by removal offers **Restore this version**, which
  returns the visit to that version's capture set by de-effecting the captures added after it — the
  **same de-effecting removal** as undo (shared machinery). Owner-only, gated behind a confirmation that
  names how many captures are removed. A **non-linear** version (one that included a now-deleted capture,
  or needs an out-of-context toggle) is **preview-only** with a calm note; `409` on the API.
- **Quick undo unchanged.** The Sources-drawer Undo stays the one-tap shortcut. Pin (the unused `pinned`
  column), in-place time-travel, and field-level diffs are documented fast-follows.

Architecture: [pipeline-versioning](../../architecture/pipeline-versioning.md).

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

- `Shell`, `CaptureActions`, `CaptureScreen` (composes region components from `CaptureRegions`)
- `PatientStrip` (absorbs identity + context + verify chip + safety chip; the auto-collapse machine)
- `PatientConflictResolver` (thin conflict band + Sources-drawer chip), `AiCreatedPatientPanel` (in the strip)
- `SessionContextCard` (+ `LineupCard`), `SessionSafetyPanel`, `NextLinedUpBar`
- `LiveReportView` + `TreatmentsList` (+ `TreatmentRow` / per-field overlay editor), the `sources-drawer`, `ReportFeedbackBar`
- `ReportHistoryButton` (E14 report-card header affordance) + `ReportHistorySheet` (timeline · read-only preview · owner restore) — `features/capture/reportHistory/`
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
- `POST /api/v1/sessions/{id}/apply-name-correction` · `POST /api/v1/sessions/{id}/unassign-patient`
  (E1 one-tap identity chips)
- `POST /api/v1/sessions/{id}/safety-flag-rejection` ·
  `POST /api/v1/sessions/{id}/confirm-carried-forward` ·
  `POST /api/v1/sessions/{id}/aftercare-dismissal`
- `POST` / `DELETE /api/v1/sessions/{id}/treatment-overlay` (AES-1102 field edit / Revert-to-AI)
- `GET /api/v1/sessions/{id}/report-versions` · `GET /api/v1/sessions/{id}/report-versions/{versionId}` ·
  `POST /api/v1/sessions/{id}/report-versions/{versionId}/restore` (E14 report version history)
- `PATCH /api/v1/tenant/settings` (incl. `highRiskClinic` — pin the safety panel)
- `GET /api/v1/patients/{id}/session-context` · `GET /api/v1/patients/search` ·
  `POST /api/v1/patients`
- `GET /api/v1/ai-usage`

## Known Gaps

- `+ New visit` resets the active context locally; the remote session is created when the first
  capture syncs (a pre-assigned patient is attached then).
- Historical review shares the report workspace but does not expose the full patient assignment
  panel.
