# Session Review

## Route

No separate route. Opens inline from Clinical Memory patient detail/timeline or a
[finder](finder.md) visit result using the Active Session Workspace structure ([capture.md](capture.md)).

## Purpose

Review one session with the same report-first structure used by the active workspace, inspect
generated output and captures, edit the title, add captures to the same evolving session, and share
a curated report with the patient.

All session states remain reviewable. State badges are informational and do not gate historical
review access.

## Primary Actions

- Add capture to continue the same session with refreshed progressive output.
- Save title.
- Open capture source preview.
- **Share with patient** (Pro; assigned visit with captures) — opens the curated share sheet
  (below).
- Rate the synthesized report with a lightweight 👍 / 👎 (Pro report only; shown once the report has
  real sections or treatments). Rendered as a quiet **end-cap after the aftercare section** (rate-after-
  reading — it never splits the clinical content, and on mobile sits just above the collapsible Sources).
  One tap records a quiet AI-quality signal and collapses to a thank-you — never a blocker. Feeds the
  eval golden-set harvester ([docs/ai_engine/evals.md](../../ai_engine/evals.md)). Bilingual + RTL-aware.

## Visible Data

- Session title, full summary, status, and actionable patient assignment.
- Clinical report with local progressive state, passive assistant-state indicators, and live
  draft/structured view switching when generated report output is unavailable.
- The treatment table, before/after media, and per-claim citations below (Pro).
- Collapsible summary.
- Collapsible extracted findings.
- Source previews, statuses, and generated capture details through clickable live draft cards.

## Treatment table (Pro)

The structured `treatments[]` render as the primary surface of the report's *Treatment performed*
section (the prose blocks mirror it) — one row per extracted treatment:
**area · product · brand · quantity · lot**.

- **Quantities are verbatim.** A row shows `quantityText` — the original dictated string in its
  original script (`۲۰ واحد`, `2 cc`) — falling back to `quantity + unit` only when no verbatim
  text exists. The doctor sees exactly what they said; that is the audit trail and the trust
  anchor.
- **Carried forward** (`same as last time`) is flagged on its row. An unconfirmed carried-forward
  **dose** shows an inline `Confirm dose` box (the synthesis's reason + a one-tap confirm) and is
  counted by the sticky verify bar — the report never reads clean/`Complete` while a carried dose
  is unconfirmed (a dose is the one field where silent completion is a safety risk). A confirmed
  row flips to `✓ Dose confirmed` in place.
- **Soft flags fix at source.** A low-confidence row and a missing-but-expected lot render quiet
  inline flags with a `Fix at source` deep-link to the originating capture — correct the capture
  text and the AI re-extracts. There is no direct treatment-field edit. Softer uncertainties render
  as calm gray footnotes beneath the list — never blockers.
- Clinical content is verbatim, never translated; direction is per-line (a Farsi row keeps `Dysport`
  / `D-4471` LTR inside RTL text). Chrome is bilingual.

## Before/after media (Pro)

The report `media` section renders before/after photo pairs with two modes — **side-by-side**
(default) and a **draggable compare slider** (drag to reveal after-over-before; reversible toggle).
Pairing is consumed from the deterministic backend `photo_pairing` metadata attached at
serialization — the rendering consumes pairs, it never pairs. Unpaired photos render as single
captioned images; media that fails to load degrades to a labelled placeholder, never a broken
image. Bilingual + RTL-aware.

## Per-claim source citations (Pro)

Treatment rows and cited prose blocks show a `↗ source` tap that opens the grounding capture in the
source preview — "tap a claim → its source capture." Same-session captures resolve locally; a
carried-forward claim that cites a prior visit fetches the capture by id. Every clinical claim is
traceable to a capture — the report's authority is that nothing is invented.

## Share with patient (curated)

The **Share** affordance on the report header opens the curation sheet (`SharePatientSheet`).
Sharing is an explicit, per-visit, outward-facing action — the doctor curates, never the AI:

- Toggle rows for each before/after photo, the patient-appropriate sections, a plain-words
  **"what we did"** list (opt-in; generic wording by default — brand names only when the tenant's
  include-brands setting is on, [account.md](account.md)), the **assessment** (opt-in, default
  **off** — clinician findings can alarm out of context), and the aftercare template.
- Internals — the treatment table, lots, uncertainty chips, raw captures, PII — are withheld
  **server-side**: the share endpoint only copies the curated snapshot, so no UI bug can leak them.
- **Preview** renders exactly what the patient will see; sending the link is explicit; the link is
  **revocable** from the same sheet.

What the patient receives: [patient-surface.md](patient-surface.md).

## Main Components

- `CaptureScreen`, historical mode
- `SourcePreviewDialog`
- `SharePatientSheet`

## Loading State

- Captures are loaded on open when a selected session has no items.

## Empty State

- `No captures loaded for this session yet.`
- Generated report area remains visible when no processed report exists.
- Progressive output is refreshed after a capture is added to previously processed material.

## Error State

- Title failures generally surface through unchanged UI or generic failure patterns.
- Source preview failures show inline preview error.

## Success State

- Title actions update visible session state and show success toasts.
- Generated outputs appear when organizing completes.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Clinical Memory workflow](../workflows/review-and-assign-patients.md)

## Related APIs

- `GET /api/v1/sessions/{session_id}/captures`
- `PATCH /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/save`
- `GET /api/v1/captures/{capture_id}/file-content`
- `POST /api/v1/sessions/{session_id}/confirm-carried-forward`
- Share create/revoke per [aes-basic-api.md](../../backend/aes-basic-api.md)

## Known Gaps

- Historical review does not have its own shareable URL.
