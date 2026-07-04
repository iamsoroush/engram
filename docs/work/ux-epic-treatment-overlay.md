# UX Epic — User-authored treatment overlay

**Status:** design proposal for owner review. Not built. Do not fold into system-state until approved.

**Fold destination (when approved + built):** [`docs/ux/screens/session-review.md`](../ux/screens/session-review.md)
(Treatment table — direct edit), [`docs/ux/screens/capture.md`](../ux/screens/capture.md) (report
surface — replace "there is no direct treatment-field edit"),
[`docs/architecture/pipeline-versioning.md`](../architecture/pipeline-versioning.md) (extend the D2
user-state overlay to treatment edits), [`docs/technical-decisions.md`](../technical-decisions.md)
(a dated decision that the deferred `edit` intent ships as a human overlay, not an AI intent), and a
new `AES-11xx` band in [`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md).

> Priority **2 of 5**. This epic realises the **`edit` intent** that
> [intelligence-layer.md §1](../intelligence-layer.md) deferred ("mutating structured-report fields
> … out of v1"), but as a **human-authored overlay** — no AI. The AI-pipeline mechanics (stable
> treatment keys, reconcile signal) are being planned separately in
> `docs/work/ai-engine-refactor-plan.md`; this doc states **requirements**, not implementation.

---

## 1. Problem & evidence

A Pro treatment row shows `area · product · brand · quantity · lot`, with `quantityText` — the
**verbatim** dictated dose string (`۲۰ واحد`, `2 cc`) — as the trust anchor
([session-review.md](../ux/screens/session-review.md)). When the extraction gets **one field wrong**
(the transcript misheard "بیست و چهار" as "بیست", so a 24-unit dose reads 20), there is **no way to
fix that field**. The only correction path is **Fix at source**: open the originating capture, edit
the transcript text, and wait for a full re-synthesis.

**Grounded in code:**

- The row is rendered by `TreatmentsList` (`features/capture/components/LiveReport.tsx`), fields
  shaped by `workspaceTreatments()` / `treatmentLabel()` in `captureModel.ts` (`quantityText` takes
  precedence over `quantity + unit`). There is **no `<input>` bound to any treatment field anywhere
  in the frontend** — confirmed by grep.
- `Fix at source` (`LiveReport.tsx` → `onFixAtSource` in `CaptureScreen.tsx`) does nothing but
  `setSourcesOpen(true)` and scroll to the Sources drawer. The row's own comment states the intent:
  *"the lot/dose is fixed by editing what was captured, then the AI re-extracts — never overwritten
  by a manual edit."*
- Editing the capture text (`PATCH /captures/{id}` → `update_capture` in `captures.py`) does **not**
  patch one field — it calls `mark_session_stale_after_source_text_update`, flipping the session to
  `queued`/stale. The debounced `session_organize` LLM job then re-runs the **whole session**
  (`reports.py` `maybe_dispatch_session_synthesis`). Because the report is keyed by the ordered
  capture-version set ([pipeline-versioning](../architecture/pipeline-versioning.md)), a text edit
  changes the content hash → the cached `report_version` no longer matches → a genuine LLM miss.

So a **one-character dose fix costs a full-session synthesis** (latency + AI budget), routes through
an unrelated surface (the Sources drawer, not the row you're looking at), and — worse — is **not
durable**: the correction lives in the transcript, and the *next* capture's re-synthesis can re-mis-
extract it. The human never truly *owns* the field.

There is one latent hook: the backend `update_session` **can** accept `extracted_metadata.treatments`
and harvest the before→after as a correction signal (`sessions.py`), but **no UI reaches it**, and it
writes the AI artifact directly (not an overlay), so a later synthesis would overwrite it.

## 2. Design goal & the contract it rests on

**Direct inline treatment-row editing, recorded as a human-owned overlay that synthesis can never
overwrite.** The substrate is the existing **D2 user-state overlay**
([pipeline-versioning](../architecture/pipeline-versioning.md)): rendered state =
`report_version ⊕ overlay`, where the overlay is authoritative and applied **after** the AI artifact.
Today the overlay holds three key classes (`report_versions.py`):

```text
OVERLAY_METADATA_KEYS = ("rejected_safety_flags", "confirmed_carried_forward", "dismissed_aftercare")
```

This epic adds a **fourth class — `treatment_overlay`** — and reuses the load-bearing invariant that
already protects the other three: `restore_report_version` excludes overlay keys, so undo/redo and
re-synthesis **never disturb a user decision**. A treatment edit becomes exactly that: a user
decision on the artifact, not part of it.

Framing decision to record: the deferred `edit` intent is delivered as a **human overlay, not an AI
intent** — the human types the truth directly; the AI is never asked to "apply an edit". This keeps
the edit deterministic, instant, cost-free, and immune to re-mis-extraction.

## 3. The design

### 3.1 Overlay entry shape (the contract)

Each edit is a keyed overlay entry, attributed and reversible:

```jsonc
"treatment_overlay": [
  { "treatmentKey": "cheeks|voluma", "field": "quantity",
    "value": "24 units", "aiValue": "20 units",
    "editedByUserId": "u_…", "editedAt": "…", "op": "edit" },
  { "treatmentKey": "…", "op": "remove", "editedByUserId": "…" },   // v2: hide a hallucinated row
  { "treatmentKey": "human:…", "op": "add", "fields": { … } }       // v2: net-new human row
]
```

Rendered row = AI-extracted row **⊕** its overlay entry. `remove` hides the AI row; `add` injects a
human-authored row keyed `human:*` (not tied to any AI row).

### 3.2 The edit surface (states + flow)

- Each treatment row gains a quiet **✎ edit** affordance (per-field on tap, or a row editor sheet on
  mobile). Editable fields: `area · product · brand · quantity · lot` (technique attributes are v2).
- Editing `quantity` (the motivating dose case) opens a small field editor prefilled with the current
  rendered value; save records the overlay entry — **deterministic, instant, no synthesis, no AI
  budget.**
- The edited field flips to a **human-owned** presentation, visually distinct from AI provenance:
  a `✎ Edited by you` chip (vs the AI spark), and a **provenance subline preserving the audit
  trail**: `24 units · corrected — dictated ۲۰ واحد`. The verbatim dictation is *never destroyed* —
  it moves to the subline so the trust anchor survives the correction.
- **Revert to AI** is one tap on the edited field (drops the overlay entry → the AI value returns).
- The `↗ source` citation stays on the row (the row still originated from a capture); the human value
  now sits on top of it.

Flow:

```text
Row: Cheeks: Voluma (Allergan) — 20 units · lot D-4471   ✎
  ↓ tap ✎ on the dose
Editor:  Quantity [ 24 units          ]  dictated: ۲۰ واحد   [Save] [Cancel]
  ↓ Save  (instant — no "Organizing")
Row: Cheeks: Voluma — 24 units ✎ Edited by you · dictated ۲۰ واحد   ↗ source  · Revert to AI
```

### 3.3 Synthesis-proof reconcile (the trust behavior)

When a *later* capture triggers a real re-synthesis and the fresh AI extraction **disagrees** with a
human-edited field, the overlay still wins on render — but the disagreement is **surfaced, never
silent** (the same "warnings over blocking" pattern as matched-vs-spoken):

```text
Cheeks: Voluma — 24 units ✎ Edited by you
   AI now reads 22 units from the latest capture.   [Keep yours (24)] [Use AI (22)]
```

`Keep yours` is the default (do nothing); `Use AI` drops the overlay entry. This makes the guarantee
concrete: **synthesis can update the row freely, but it can never overwrite your value without you
seeing it and choosing.**

### 3.4 Copy (en, with fa notes)

| Surface | English | fa note |
| --- | --- | --- |
| Edit affordance | `Edit` | «ویرایش» — chrome via `t()` |
| Human marker | `Edited by you` | «ویرایش شما»; attribute others as `Edited by {name}` |
| Provenance subline | `corrected — dictated ۲۰ واحد` | the dictation stays clinical CONTENT, not translated |
| Revert | `Revert to AI value` | «بازگردانی به مقدار هوش مصنوعی» |
| Reconcile | `AI now reads {x}. Keep yours / Use AI` | numbers tabular; row RTL-mirrored |
| Save toast | `Treatment updated` | «درمان به‌روزرسانی شد» |

Field **values** (product, lot, dose) are clinical CONTENT — entered/kept in the report language,
per-line RTL (a Latin brand/lot stays LTR inside an RTL row). Only the chrome routes through `t()`.

## 4. Contract requirements (hand-off to `ai-engine-refactor-plan.md`)

Stated as requirements — the AI-engine track owns the mechanics:

1. **Stable treatment keys.** Each extracted treatment needs a **stable identity that survives
   re-synthesis**, so an overlay entry re-binds to the right row after the artifact regenerates.
   Today treatments are an unkeyed JSON array (re-extraction may reorder/re-split them). This is the
   same problem the safety overlay already solved with a stable `flag_key` (D2/D7) — treatments need
   the analogue. Recommendation to evaluate: a content-anchored key (source-capture id + normalized
   area+product) with a reconcile fallback when a row splits/merges.
2. **Overlay application extended to treatments.** `report_version ⊕ overlay` must fold
   `treatment_overlay` at render (today it folds flags/confirmations/aftercare); `restore_report_version`
   must add the new key to the excluded set so undo/redo never lose an edit.
3. **A reconcile signal on the payload.** When fresh extraction disagrees with a human-edited field,
   emit **both** values (`aiValue` + the human `value`) so the UI can offer Keep/Use-AI — never a
   silent overwrite.
4. **Projections read the overlaid value (safety-critical).** Cross-visit projections —
   recall, **lot-recall cohorts**, smart-lists ([D4 recompute-from-source](../architecture/pipeline-versioning.md)) —
   must read `report_version ⊕ overlay`, not the raw AI artifact. If a clinician **corrects a lot
   number**, the recall cohort ([Lists tab](../ux/screens/patients.md)) must use the *corrected* lot.
   This is the single highest-stakes requirement.
5. **Eval note.** The overlay itself is not an AI job (not eval-gated). But adding **stable keys** to
   the synthesis output is a change to the `session_organize` contract → run
   `apps/ai_engine/eval/run_all.py` and confirm no extraction regression (per
   [CLAUDE.md §4](../../CLAUDE.md)).

## 5. Tier & persona behaviour (per [foundation.md](../ux/foundation.md))

- **Pro only.** Basic has **no structured treatment table** — [AES-108](../ux/aesthetics-stories.md)
  fixed that detail stays free-text in Basic (structure is Pro-by-extraction). A Basic user already
  edits their note text directly; there is nothing to overlay. State this so the epic isn't misread
  as re-introducing structured entry into Basic.
- **Owner-default editing.** Reuse the [pipeline-versioning permissions](../architecture/pipeline-versioning.md)
  point (undo v1 = owner-only) and the fast-follow tenant **edit-policy** (strict = owner-only ·
  standard = owner+admin · open = any staff). Every edit is **attributed** (`Edited by {name} · time`,
  [AES-901](../ux/aesthetics-stories.md)).
- **Never block for non-owners.** Under a permissive policy a non-owner edit applies + is attributed.
  Under a restrictive policy, a non-owner's correction **routes as a suggestion to the owner** (reuse
  the `suggested_reassignment` suggest-to-owner pattern, [AES-906](../ux/aesthetics-stories.md)) —
  permissions decide *apply vs. suggest*, never *stop*. (v2; v1 simply shows read-only rows to
  non-permitted roles.)

## 6. Edge cases

- **Verbatim preserved.** A dose correction moves the dictation to the provenance subline; the audit
  trail (`quantityText`) is never deleted, only demoted below the human value.
- **Re-synthesis disagreement** → the §3.3 Keep/Use-AI reconcile. Never silent.
- **Source capture undone/deleted.** An `edit` entry is an edit *of* an AI row; if that row's source
  capture is de-effected ([capture.md undo](../ux/screens/capture.md)), the row disappears and its
  `edit` entry is dropped with it. A v2 `add` (human-authored row with no AI source) **survives**
  capture undo — it's independent human content.
- **Editing a carried-forward dose.** Changing a carried dose's value both records an `edit` **and**
  implicitly satisfies the `confirm-carried-forward` overlay (you've stated the real value) — collapse
  the two so the row doesn't still ask "Confirm dose" after you edited it.
- **Low-confidence row.** A human edit to a low-confidence field clears the low-confidence flag (a
  human confirmed the value) — the row stops rendering the amber uncertainty chip.
- **Multi-seat concurrency.** Two staff edit the same field → last-write-wins on the keyed entry,
  both attributed; no merge conflict UI (a field is atomic).
- **Offline.** The overlay is local-first (like confirmations today, mirrored in `captureModel.ts`);
  an edit queues via the outbox and is authoritative locally immediately.
- **Share sheet.** The curated "what we did" and any shared treatment list use the **corrected**
  values; the withholding contract ([session-review.md](../ux/screens/session-review.md)) is
  unchanged (raw captures/lots still withheld server-side).

## 7. Incremental build plan + AES-### candidates

Proposed as **candidate epic E11** (new band; not yet registered).

1. **AES-1101 — `treatment_overlay` contract.** Add the fourth overlay class + stable treatment keys
   (coordinate with `ai-engine-refactor-plan.md`); extend `⊕` render and `restore_report_version`
   exclusion. No UI yet — shadow the shape.
2. **AES-1102 — Inline field editing + provenance.** The ✎ affordance, field editor, `Edited by you`
   marker, verbatim provenance subline, Revert-to-AI. Deterministic, instant, no synthesis.
3. **AES-1103 — Synthesis-proof reconcile.** Keep-yours / Use-AI on a fresh-extraction disagreement.
4. **AES-1104 — Projection correctness (lot/recall safety).** Recall, lot-recall, and smart-lists read
   the overlaid values. The safety-critical piece — do not ship 1102 to production without it for
   `lot`.
5. **AES-1105 — Attribution + owner/policy gating.** `Edited by {name}`; owner-default; edit-policy
   presets.
6. **AES-1106 (⊕) — Row add / remove.** Hide a hallucinated row; add a net-new human treatment.
7. **AES-1107 (⊕) — Non-owner suggested correction.** Restrictive-policy edits route to the owner.

## Decisions & open questions

**Resolved (owner review, 2026-07-04):**

- **Q1 · Stable-key strategy — content-anchored.** Deterministic, backend-computed keys; the full
  mechanics (Unicode-general normalization, `priorKey` tie-breaker, re-bind pass, ordinal
  collision limitation) live in [ai-engine-refactor-plan.md §4](ai-engine-refactor-plan.md).
  That plan also adds the **language-portability contract** this epic inherits: every extracted
  structured payload gains a `lang` stamp, and synthesis emits a canonical English `areaCode`
  the key anchors on — so keys survive a report-language switch and non-fa/en clinics (e.g.
  Turkey) without fragmenting overlay bindings. (AES-11xx stories get registered in
  `aesthetics-stories.md` when this epic is approved to build, per §7.)
- **Q2 · v1 scope — field-edit only** (row-remove/add stay v2, AES-1106).
- **Q5 · Harvest signal — YES:** human field edits are harvested as structured AI-feedback
  (`kind=correction, ai_output_type=treatment`, field granularity) feeding exact-match eval cases
  (see [eval-improvement-plan.md](eval-improvement-plan.md) Part 3a).

- **Q3 · Verbatim handling — subline demotion** (owner review, round 3 — 2026-07-04): the dictated
  value moves to the provenance subline (`corrected — dictated ۲۰ واحد`), never struck-through
  inline. The audit trail survives; the human value leads.
- **Q4 · Auto-confirm — YES** (owner review, round 3 — 2026-07-04): editing a carried-forward dose
  auto-satisfies the confirm blocker — the edit *is* the confirmation; the row never asks
  "Confirm dose" after a human stated the value.

All five questions are now resolved — the epic is decision-complete and ready to build (register
the AES-11xx band on build start).
