# Session Review

## Route

No separate route. Opens inline from Clinical Memory patient detail/timeline or `/#search` using the Active Session Workspace structure.

## Purpose

Review one session with the same report-first structure used by the active workspace, inspect generated output and captures, edit the title, and add captures to the same evolving session.

All session states remain reviewable. State badges are informational and do not gate historical review access.

## Primary Actions

- Add capture to continue the same session with refreshed progressive output.
- Save title.
- Open capture source preview.
- Rate the synthesized report with a lightweight 👍 / 👎 (Pro report only; shown once the report has
  real sections or treatments). Rendered as a quiet **end-cap after the aftercare section** (rate-after-
  reading — it never splits the clinical content, and on mobile sits just above the collapsible Sources).
  One tap records a quiet AI-quality signal and collapses to a thank-you — never a blocker. Feeds the
  eval golden-set harvester (`docs/ai_engine/eval-epic.md` §1b). Bilingual + RTL-aware.

## Visible Data

- Session title, full summary, status, and actionable patient assignment.
- Clinical report with local progressive state, passive assistant-state indicators, and live draft/structured view switching when generated report output is unavailable.
- **Before/after media (Pro):** the report `media` section renders before/after photo pairs with two
  modes — **side-by-side** (default) and a **draggable compare slider** (drag to reveal after-over-before).
  Pairing is the deterministic backend `photo_pairing` (the rendering consumes pairs, it never pairs);
  unpaired photos render as single images. Bilingual + RTL-aware. See
  [redesign-pro-report §2.4](../redesign-pro-report.md).
- **Per-claim source citations (Pro):** treatment rows and cited prose blocks show a `↗ source` tap that
  opens the grounding capture in the source preview — "tap a claim → its source capture" (assistive +
  cited). Resolves same-session captures locally; fetches by id for a carried-forward claim that cites a
  prior visit. See [redesign-pro-report §2.3](../redesign-pro-report.md).
- Collapsible summary.
- Collapsible extracted findings.
- Source previews, statuses, and generated capture details through clickable live draft cards.

## Main Components

- `CaptureScreen`, historical mode
- `SourcePreviewDialog`

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

- [Generate structured session report](../workflows/save-session.md)
- [Clinical Memory workflow](../workflows/review-and-assign-patients.md)

## Related APIs

- `GET /api/v1/sessions/{session_id}/captures`
- `PATCH /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/save`
- `GET /api/v1/captures/{capture_id}/file-content`

## Known Gaps

- Historical review does not have its own shareable URL.
