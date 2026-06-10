# Active Session Workspace

## Route

- `/`
- `/#active-session`

## Purpose

Primary working screen for building and reviewing a session from audio, photo, and text captures. The same workspace structure is reused for historical session review from Clinical Memory and Search.

> **Report surface redesigned (Epics C/E shipped; simplified 2026-06-07).** The tabs are now `Captures`/`Live report` with per-capture effect chips and a **template-driven live report that is rebuilt deterministically (no LLM, no AI job) as each capture lands — there is no Generate button** (Pro = grouped-by-type sections, Basic = chronological; out-of-context captures are excluded). There is **no manual "Verify report"** — a session shows an auto-derived **Complete** state instead. [redesign-capture-surface.md](../redesign-capture-surface.md) is **authoritative for the report surface**; the report-tab sections below (`Generate Structured Report`, the `Live draft`/`Structured report` tabs, the manual generate/draft-state flow, and any "verify" wording) are retained as historical context and superseded by that doc. The capture/photo/note, assignment, and source-preview behavior here remains current.

## Primary Actions

- Start audio capture.
- Take photo opens the Add photo bottom sheet, where staff can take a new camera photo or choose from the device library before saving.
- Write note.
- Rename current session.
- Assign or reassign patient, including before the first capture and after verification.
- Generate Structured Report from the report header.
- Verify structured report.
- Start a new session.
- Review a historical session inline from Clinical Memory or Search.
- Add capture from historical review, which returns the same session to the active workspace.
- Open a source preview.

## Visible Data

- Mobile-first app header with centered `Memora`, a left menu affordance, and a compact user/avatar area.
- Session summary with `Current session`, verified chip, patient context, capture count, updated time, and compact New session action.
- Separate patient context card with patient avatar, assignment source, and Edit patient action.
- Single `Clinical report` card with `Live draft` and `Structured report` tabs.
- Report header with `Clinical report`, compact status, and Generate action when generation is available.
- Report toolbar with view selection inside the Clinical report card.
- Report footer with a toggleable animated checkbox for verifying the structured report.
- Assigned patient controls are visually actionable and show smaller assignment source text under the patient name only when a patient exists.
- Patient assignment opens a mobile-first bottom sheet from Edit patient with current-session context, suggested matches, local/API-backed search, and inline patient creation.
- Clinical report section that always exists, including before the first capture.
- Recording audio opens as a mobile-first bottom sheet with timer, animated levels, pause/resume, stop/save, discard, background continue, and a styled `Use audio file instead` fallback.
- Add photo opens as a mobile-first bottom sheet with camera and device-photo options, a large preview area, disabled save actions until a photo is selected, and security copy.
- Live draft capture cards that update immediately when audio, photo, or text captures are added.
- Audio captures render playback inline in the draft.
- Audio transcript and photo caption text render fully inline in the draft so review does not require opening a detail card.
- Audio transcript and photo caption headings show whether the text is still AI-generated or was edited by staff.
- Captures that are the active patient action source show action badges such as `Patient assigned` and, when applicable, `Patient created`. Older AI source captures lose the active action badge when a later patient action supersedes them.
- When AI creates and assigns a patient from audio identity, the patient context stays in the Active Session and shows an inline completion/verification panel for name, national ID, phone, and date of birth.
- When AI deterministically matches an existing patient, the Active Session updates the patient context and notifies staff that the match was made by AI.
- When AI lands on a **partial (fuzzy)** match (e.g. spoke `معاصد`, transcribed `معاضد`), the capture is **not silently assigned**: it shows the matched-vs-spoken identity and one-tap **Keep match / Create new instead / Choose another / Edit details** quick actions. A close match auto-applies (reversible) only under the `balanced`/`lenient` match-strictness setting. See [redesign-capture-surface.md](../redesign-capture-surface.md) "Partial-match resolution" (authoritative) and the [review-and-assign-patients workflow](../workflows/review-and-assign-patients.md).
- Photo captures render inline in the draft with a compact thumbnail and full caption/analysis text beside it.
- Note captures show full decorated text inline plus an expandable raw note section.
- Capture item overflow controls open per-capture settings for rename and delete. Deleting a capture removes it from the draft feed and moves any generated structured report back to draft/stale state.
- Structured reports render clinic information, patient information, and body as distinct sections. Clinic and patient information come from template/session context; the body is backend-owned markdown. Photos appear in the body with generated captions under the image and avoid repeating captions as body paragraphs.
- Source captures are no longer duplicated in a separate expandable section outside the Clinical report card; the live draft cards are the source review surface.
- During structured report generation, the report surface switches to `Structured report` immediately and uses assistant-style organizing feedback until the full body is available.
- The live draft remains reviewable outside the locked generation moment; users can switch between `Live draft` and `Structured report`.
- `Structured report` is disabled until at least one capture exists and explains that the user must create a capture first.
- Progressive report states: `Draft`, `Structured`, and `Verified`. Adding a new capture or changing the patient after generation returns the state to `Draft` until the user generates again.
- Subtle report progress indicators for `Draft`, `Structured`, and `Verified` in the report header; verified uses a green check treatment only when the report is verified.
- Summary and extracted findings are not separate cards in the mobile-first Active Session shell.
- Capture source previews. Audio and photo captures open mobile-first detail sheets from live draft items, showing the source preview, captured metadata, editable transcript/caption text, edit attribution, and an inline transcript copy control.
- In-progress capture status chips use only `Syncing`, `Uploading`, or `Processing`; type-specific working copy such as `Transcribing audio` belongs inside the generated transcript/caption area. Completed captures do not show technical status in the card.
- Expandable generated transcript/caption/decorated text.
- Capture safety banner only when the user needs reassurance or local data safety is at risk.

## Main Components

- `Shell`
- `CaptureActions`
- `CaptureScreen`
- `TextCaptureSheet`
- `AddPhotoSheet`
- `AudioDialog`
- `SourcePreviewDialog`

## Loading State

- Source previews load cached blobs first, then protected backend file content.
- When captures are saved locally but not available everywhere, staff see reassurance such as `Offline · Captures are saved on this device`.

## Empty State

- Active mode with no captures still shows the Active Session Workspace and an empty report surface.
- Historical review with no loaded captures shows the empty live draft surface.

## Error State

- Toasts for storage, audio conversion, save, and user-action failures.
- Empty photo selections are rejected before save/upload and prompt the user to open the camera or gallery again.
- Critical local-save or storage issues warn the user because data safety is at risk.
- Source preview unavailable placeholder or inline preview error.

## Success State

- Capture appears immediately after local save.
- Toasts confirm local save, memory update, title update, assignment, AI patient match/creation, and structured report generation start.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Generate structured session report](../workflows/save-session.md)

## Related APIs

- `POST /api/v1/captures`
- `POST /api/v1/sessions/{session_id}/save`
- `POST /api/v1/sessions/{session_id}/assign-patient`
- `POST /api/v1/sessions/{session_id}/verify`
- `GET /api/v1/patients`
- `POST /api/v1/patients`
- `PATCH /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/captures`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- `+ New session` resets the active context but does not create an empty remote session until the first capture is available beyond the device; assigning a patient before the first capture creates a local empty workspace context that is attached later.
- Report, summary, extracted findings, and assistant-state language use stable contracts plus local live draft output until final session artifacts are integrated.
- Report layout keeps a stable body height during organizing states so captures remain visible below instead of being displaced by loading states.
- Historical review currently shares the report workspace but does not yet expose the full patient assignment panel.
