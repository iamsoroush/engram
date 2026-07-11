# UX Epic — report version history (navigate, preview, restore)

**Status:** design resolved (2026-07-11) — §2 developed, §4 answered below with rationale; building on
`p3/report-history`. Direction agreed with the user at the 2026-07-04 review ("instead of the ugly Undo
button, a versioned history-like UI to navigate between report versions").

**Fold destinations (when built):** [`docs/ux/screens/capture.md`](../ux/screens/capture.md)
(report card + Sources drawer — replaces/augments the "Undo last capture" affordance),
[`docs/architecture/pipeline-versioning.md`](../architecture/pipeline-versioning.md) (status
updates — the version store gains its first HTTP surface + the D5 GC decision),
[`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md) (new **E14** band).

---

## 1. Why

The current undo surface is a single "Undo last capture" button in the Sources-drawer header —
functional but crude: one step, one direction, no visibility into what changed. Yet the substrate
underneath is already a full version store: `session_report_versions` records **every** synthesis
result, content-addressed by the ordered capture set, with a `pinned` column and a proven
restore path (`restore_report_version`, used by capture-undo today). The UI just doesn't expose it.

## 2. Design (resolved)

### Entry — one quiet affordance on the report card

A quiet **History** control (the existing `ClockHistoryIcon`) in the **report-card header actions**,
grouped with the AI spark / updating spinner / Share. It is the single mount point in
`CaptureScreen.tsx` (one line of JSX); everything else lives in a new `features/capture/reportHistory/`
module. Pro + assigned/active visits only (Basic has no synthesis chain — §3). It opens the timeline as
a bottom sheet **over** the report (capture bar stays underneath), consistent with the finder overlay
pattern.

### Timeline — the version list

A newest-first list, one row per stored `session_report_version` for the session:

- **time** (`generated_at`, `Updated: HH:MM` label vocabulary from [states.md](../ux/states.md)),
- a **trigger label** derived from the capture-set delta vs the previous version — `Photo added` /
  `Audio added` / `Note added` / `Capture removed` / `Transcript edited` / `Caption edited` /
  `Marked out of context` / `First report` / `Report updated` (fallback). The label is **chrome**
  (bilingual via `t()`), so the backend returns a structured `trigger {kind, captureType?, count?}` and
  the client localizes it — never a server-authored string.
- **capture count** (in-context captures in that version),
- **provenance, demoted** — `generated_by` + `generated_at` in a quiet subline. (Model/prompt version is
  **deliberately not stored** per D1 — the version key ignores it — so per-version model provenance is
  not available; we surface what exists rather than inventing it.)
- The row matching the **current** capture set is tagged `Current`; a **restorable** past row exposes a
  `Restore` action (owner-only — below).

### Preview — read-only, self-contained, overlay-on-top

Tapping a row fetches that version's artifacts and renders the report **read-only inside the sheet**
(the same `LiveReportView` presentation, driven by a synthesized `CaptureSession` built from the
version's `artifacts` — `canEditTreatments=false`, edit/confirm callbacks omitted). A banner reads
`Viewing the version from HH:MM · Back to current`.

The **user-state overlay is applied on top** of whichever version renders (the live session's
`rejected_safety_flags` / `confirmed_carried_forward` / `dismissed_aftercare` / `treatment_overlay` are
merged into the synthesized preview session) — user decisions are **never time-traveled away**
(ground-truth invariant, pipeline-versioning D2). This is a client-side merge; no backend overlay
storage changes.

**Why in-sheet, not time-travel-in-place:** the mount constraint (one small integration point in
`CaptureScreen.tsx`, trivial rebase after the parallel tier-convergence epic restructures that file)
rules out swapping the live report card's content in place for v1. In-sheet preview reuses the exact
report presentation, stays fully self-contained, and still satisfies "renders it read-only in the report
surface" in spirit. Time-travel-in-place is a documented fast-follow the settled report region can adopt.

### Restore — de-effect back to a version's capture set (revert; owner-only)

**v1 restore semantics = revert-captures**, generalized from today's one-step undo to N steps.
`Restore` on a past version returns the session to **that version's capture set** by soft-deleting the
captures added after it, through the **exact same de-effecting machinery** capture-delete/undo uses
(`apply_active_patient_assignment` → orphan-AI-patient archive → `find_report_version_for_current_set`
cache-hit `restore_report_version` **or** recompute → `sync_patient_safety_flags` +
`apply_safety_reconciliation`). So:

- restore semantics are **shared** with capture-undo (P0-8 stays green — same leaf helpers, exercised by
  the same de-effect path),
- the report ⊕ capture-set **invariant holds** (no "pinned/stale disagreement" state to design in v1),
- **no pipeline change** is required (the epic's boundary) — restore is an existing consumer of the
  store, not a new writer.

**Reachability guard (safety).** Restore is offered **only for versions reachable by removal alone** —
i.e. the version's capture-id set is a subset of the current non-deleted set **and** each surviving
capture's out-of-context membership matches the version's. Anything else (a version that included a
now-deleted capture, or needs an out-of-context toggle) is **preview-only** with a calm note. This is the
overwhelmingly common "kept adding captures" timeline; the non-linear cases are honestly deferred rather
than served wrong. The backend computes reachability + the removal set from the `version_id` (the client
never orchestrates multi-delete — CLAUDE.md §5).

**Destructive-action honesty.** Because restore removes captures (potentially photos/audio), it is gated
behind a confirmation that **names exactly what will be removed** ("Restoring this version removes the 3
captures added after it: 2 photos, 1 note"), is **owner-only** (identical to undo's gate), and the
captures are **soft-deleted** (recoverable at the data layer). The action is honestly a generalization of
undo — which is what the user asked this UI to replace.

**Quick undo stays.** "Undo last capture" remains the one-tap shortcut in the Sources drawer (it is
"restore to the previous version" with N=1 — same endpoint the delete path already uses); the timeline is
its richer, multi-step face.

### Backend surface (3 new session-scoped routes, `app/sessions_api.py`)

- `GET /api/v1/sessions/{id}/report-versions` — list metadata `{ versions: [{ id, captureSetHash,
  captureCount, generatedAt, createdAt, isCurrent, restorable, trigger, generatedBy }] }`
  (`staff_or_admin_required`).
- `GET /api/v1/sessions/{id}/report-versions/{versionId}` — the version's artifacts, session-shaped for
  read-only preview (`staff_or_admin_required`).
- `POST /api/v1/sessions/{id}/report-versions/{versionId}/restore` — revert-to-version
  (`staff_required` + in-service owner check `can_remove_capture`); returns the updated `session` payload,
  exactly like `DELETE /captures/{id}`. `409` when the version isn't reachable by removal.

## 3. Boundaries

- **Pro-first:** versions are synthesis artifacts; Basic's deterministic report rebuilds from captures
  and has no stored version chain (Basic keeps simple capture undo). The History affordance renders on Pro only.
- **No pipeline changes:** this epic consumes the existing store + overlay fold. Confirmed against the
  worker — nothing new needed there.
- **Version GC (D5) is a separate, documented decision** (§4 Q2) — not implemented here.

## 4. Open questions — resolved

**Q1 · Restore semantics v1: revert / pin / both? → revert-captures only (pin is a fast-follow).**
Revert reuses the proven `restore_report_version` + de-effect path verbatim (P0-8 semantics shared),
preserves the report⊕capture-set invariant (no new disagreement state), and needs **no pipeline change**.
Pin (make a version authoritative without touching captures) is attractive and non-destructive, but doing
it correctly requires the synthesis dispatch/staleness sweep to *respect* the pin — a pipeline change this
epic explicitly excludes — and introduces a genuinely new "pinned to an earlier version; N newer captures
not reflected" user-facing state to design. The `pinned` column exists and is **currently unused**, so pin
is clean greenfield when we choose to build it. **Decision: ship revert v1; pin fast-follow.** (Matches the
seed's own recommendation.)

**Q2 · Timeline depth / bounded ring (ties to D5 GC)? → v1 shows all stored versions; GC stays a
separate decision, recommended below.** No prune code exists today; per-session version counts are
naturally small (a handful of synthesis passes per visit), so an unbounded *per-session* timeline is fine
in practice for v1 — browsing does not worsen the cross-session storage-growth problem GC addresses. The UI
is built to degrade gracefully when GC later truncates the list (it shows what's stored). **Recommended D5
policy (owner to confirm — light hand-back, not a v1 blocker): keep the last 20 unpinned versions per
session + all pinned + always the current, GC the rest.** GC implementation is a fast-follow in
pipeline-versioning, not this epic.

**Q3 · Show version diffs, or is trigger-labeling enough? → trigger labels + capture count for v1; the
preview is the diff.** A per-version read-only preview already lets the clinician *see* each version in
full; a computed field-level diff (report prose / treatment rows) adds real complexity (structured-diff
algorithm + rendering) for marginal v1 value. **Decision: trigger label + count + timestamp per row; no
inline field diff in v1** (fast-follow).

**Q4 · Owner-only restore, or tenant edit-policy presets? → owner-only (identical to undo today).**
Restore *is* the de-effecting removal, so it must share undo's gate exactly (`can_remove_capture` =
session owner). Preview/navigate is available to anyone who can view the session (read-only, ungated). The
3-mode edit-policy presets (strict/standard/open) are the **same documented fast-follow** they are for undo
and treatment-overlay edits — not a v1 blocker.

## 5. v1 scope / fast-follows

**In v1:** History affordance → timeline (trigger label + count + demoted provenance) → read-only
overlay-on-top preview with the viewing banner → owner-only revert-restore (reachable versions) with a
capture-naming confirmation; quick-undo unchanged. 3 backend routes; hermetic e2e for
history+preview+restore; P0-8 unchanged/green; both-language screenshots.

**Fast-follows (documented, not built here):** pin (Q1); time-travel-in-place preview; field-level version
diffs (Q3); D5 GC/bounded-ring (Q2); 3-mode edit-policy presets for restore (Q4); restore to non-linear
(out-of-context / re-add) versions.

## 6. Hand-back (owner decisions, non-blocking)

1. **D5 GC ring size/policy** — the recommended "last 20 unpinned + all pinned + current per session" is a
   retention/COGS call; confirm or adjust when GC is scheduled.
2. **Restore edit-policy** — v1 keeps restore owner-only (like undo). If the clinic wants
   admins/assistants to restore, that rides the shared 3-mode edit-policy fast-follow.
