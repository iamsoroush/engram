# Pipeline versioning (capture → report → patient memory)

> **Goal.** Make the AI pipeline an **incremental, memoized computation over versioned inputs**, so that
> (1) **undo/redo restore prior state deterministically** instead of re-generating it (no "wrong
> entries"), (2) **LLM tokens are saved** by reusing a stored output whenever its exact input set
> recurs, and (3) **everything stays consistent** — the rendered report, its structured entities
> (treatments, safety flags, aftercare), and the cross-visit patient projections are always a function
> of the current inputs. Capture undo (the Sources drawer's "Undo last capture" / per-capture
> Delete — [ux/screens/capture.md](../ux/screens/capture.md)) is the first consumer.

## Status (built vs pending)

**Built:**

- The `SessionReportVersion` store (`session_report_versions`): immutable, content-addressed
  snapshots keyed by `capture_set_hash` (the ordered in-context capture-version set), with
  `pinned` rows exempt from future GC (`services/report_versions.py`). Each version also records the
  **`patientId` it was synthesized for** (inside `artifacts`, out of the restored key set): the
  capture-set hash is patient-blind, so a cache-hit is scoped to the session's current patient — a
  version made under a former patient never restores onto a reassigned session (its carry-forward doses
  + safety-reconcile decisions belong to that other patient). A version is keyed and its freshness
  signature stamped from the **job-START capture-set snapshot**, so a fix-at-source capture edit that
  lands mid-synthesis can't stamp a stale report "current" or store pre-edit artifacts under the
  post-edit hash — the completion detects the mismatch, keeps the report stale, and dispatches a
  follow-up (`worker.py`).
- Undo/delete **cache-hit restore**: returning to a previously-seen capture set restores the
  stored version deterministically (no LLM) and re-syncs the patient's safety flags **and re-applies the
  reconcile decisions** (parity with the synthesis-completion path — `services/captures.py`).
- **E14 report version history** — the store's first HTTP surface: `GET …/report-versions` (timeline;
  trigger label derived from the capture-set delta, `restorable`/`isCurrent` flags),
  `GET …/report-versions/{id}` (a version's artifacts for read-only preview), and
  `POST …/report-versions/{id}/restore` (owner-only **revert** to a version's capture set — de-effects the
  captures added after it via the **same** removal machinery as undo, so P0-8 semantics are shared;
  `409` for a non-linear/unreachable version). Reads live in `services/report_history.py`, the
  restore alongside `delete_capture` in `services/captures.py`, and the pure trigger/reachability helpers
  in `services/report_versions.py`. Surface: [ux/screens/capture.md](../ux/screens/capture.md) "Report history".
- **D7 safety-reconcile** end-to-end (reconcile pass in synthesis → `apply_safety_reconciliation`
  on the patient projection), with its eval suite wired into `run_all.py`.
- **D3 staleness read-trigger** for patient memory (`maybe_refresh_stale_patient_memory` on
  patient-open/line-up) plus the background quiescence sweep.
- **D2 treatment overlay (AES-1101)** — a **fourth** overlay class, `treatment_overlay`: human field
  edits on treatment rows, bound to a deterministic content-anchored `treatmentKey`, folded at
  render/projection (`services/treatment_overlay.py:effective_treatments`), re-bound after each
  synthesis (with a no-LLM `{aiValue, value}` reconcile diff), and excluded from restore. The
  **editing UI is now built** (AES-1102..1105 — the per-field ✎ editor, `Edited by you` +
  provenance/reconcile, orphan chip, Q4 auto-confirm collapse —
  [ux/screens/session-review.md](../ux/screens/session-review.md)). See D2 below +
  [backend/processing.md](../backend/processing.md).

**Pending:**

- **D5 GC / bounded ring** — no prune code exists yet; versions accumulate (pins are recorded but
  nothing is collected). Now **user-visible** via E14's browsable timeline (per-session counts are small,
  so v1 shows all stored versions). Recommended policy when GC is scheduled (owner to confirm): keep the
  **last 20 unpinned versions per session + all pinned + always the current**, GC the rest — safe because
  a lost old version only costs an occasional recompute, never correctness (D5).
- **`patient_history_version` keyed cache** — no such model; patient memory recomputes without a
  content-addressed cache.

**Divergence from D2 as written:** the user-state overlay is not a separate keyed table — it lives
in `session.extracted_metadata` (keys `rejected_safety_flags`, `confirmed_carried_forward`,
`dismissed_aftercare`, `treatment_overlay`) and is applied at restore/render time. The invariant holds
(a restore never overwrites user decisions: `restore_report_version` copies only artifact keys, so the
overlay keys survive untouched); only the storage shape differs.

## The version DAG

```
capture ──► capture_version          (a specific processed capture: this transcription/caption/detail)
              │
              ▼
{ ordered, in-context capture_versions } ──► report_version
              │        (one holistic synthesis pass; bundles prose + treatments + safety flags +
              │         aftercare selections + sourceReferences)
              ▼
{ a patient's session report_versions } ──► patient_history_version   (Job-4 memory: summary, card, hero)
```

Each edge is **memoized**: the child is keyed by its inputs, so when an input set **recurs** (the
defining case: an **undo** returns the session to a previously-seen capture set) the stored child is
**reused** — no LLM call. A forward edit (add a capture) is a new set → a genuine miss → it runs. So the
token win is real and concentrated on **undo / redo / re-add-the-same**, not on every edit.

## Decisions

### D1 — Key on the input set only; ignore model/prompt version (manual re-run is the escape hatch)
A `report_version`'s key is the **ordered list of in-context `capture_version` ids** (order matters —
correction/supersede chains reference earlier captures; in/out-of-context membership is part of the
key). We deliberately **do not** include the model/prompt version in the key. Consequence: after a model
or prompt change, old cached outputs are **not** auto-regenerated — that's acceptable; a **manual
"re-run"** (cache-bust) is the path to refresh historical artifacts when desired. Keeps the key simple
and avoids mass invalidation churn.

### D2 — Immutable AI output + a separate user-state overlay
A `report_version` is the **pure AI artifact** — immutable and cacheable. Clinician **decisions on** it —
carried-forward-dose confirmations, aftercare opt-outs, **safety-flag rejections** — are **not** part of
it; they live in a separate, key-addressed **overlay**. Rendered state = `report_version ⊕ overlay`.
This is the load-bearing invariant: restoring/reusing a cached version never resurrects or loses user
state (the exact bug class hit repeatedly — see the worker's `preserved_confirmations`). The overlay is
keyed so a decision sticks to the thing it was made about (e.g. a safety flag by its stable key).

**Fourth overlay class — `treatment_overlay` (AES-1101).** A clinician **field edit** on a treatment row
(area·product·brand·quantity·lot) is a decision *on* the artifact, not part of it, so it is an overlay
entry keyed by a stable **`treatmentKey`** — the deterministic, backend-computed, content-anchored key
`t|<areaCode|norm(area)>|norm(product)|<first sourceCaptureId>` (Unicode-general `norm`; ordinal `#n` on
collision), anchored on the synthesis-emitted canonical `areaCode` so it is **language-independent** (a
report-language switch or a non-fa-en clinic can't fragment the binding). An LLM-emitted opaque id was
rejected: independent synthesis runs have no memory, so it could only be stable by echoing prior ids —
failing precisely on the hard split/merge case — whereas a content anchor is reproducible by
construction (the same pattern the safety `flag_key` proved). Two supports: a soft **`priorKey` echo**
(the model repeats a prior row's key as a tie-breaker, never authoritative) and a deterministic
**re-bind pass** after each synthesis (exact key → bound; **priorKey-first** — a fresh row echoing the
entry's key re-binds *even across an area re-slug*, checked before the area filter that would otherwise
reject it; shared source-capture + normalized area → re-bind; else the entry is **parked in
`treatment_overlay_orphans`** — surfaced as a review chip, never deleted — and re-attempted on the next
synthesis, so a row that reappears re-binds out of the orphan list). A human edit is therefore never
destroyed by a re-key or a `treatments: []` run. On re-bind the entry's `aiValue` is refreshed so a
fresh-extraction disagreement surfaces as `{aiValue, value}` (Keep-yours / Use-AI) — **never a silent
overwrite, no LLM**. `carried_forward_key` (the confirm-dose id) is anchored on the same
`areaCode|norm(product)`, so a confirmed carried dose stays confirmed across a reword / language switch. Projections (recall, lot-recall cohorts, smart lists,
patient-memory brief) read `report_version ⊕ overlay` via one `effective_treatments()` fold, so a
corrected lot/dose is authoritative everywhere. Accepted limitation: two same-area+product rows from one
capture collide (disambiguated by the ordinal suffix; the reconcile signal surfaces any mis-bind).

### D3 — Patient memory stays lazy; staleness propagates, no new queue
Synthesis does **not** enqueue the patient-memory job (it is read/line-up-triggered — `worker.py`). We
keep that. When a session that **already contributed** to a patient's history is later edited/undone, we
**mark that patient's memory stale**; the existing **read-trigger** (interactive, high — recompute when
someone opens the patient) and **stale-sweep** (background, low) reconcile it. No new queue — the work is
**correct staleness propagation** from a session change to its patient. A `patient_history_version` is
keyed by the set of its sessions' current `report_version`s, so it too can cache-hit when that set
recurs.

### D4 — Patient-level projections are derived from current report_versions (recompute-from-source)
Entities that leave their source session — **safety flags** (`Patient.safety_flags`), **patient
memory/history** (Job-4 aggregate), **treatments** (cross-visit recall + carry-forward) — are a
**deterministic function of the sessions' current `report_version`s**, recomputed **from source** on any
contributing change, **never incrementally patched**. This guarantees they're live + consistent with no
drift.
- **Safety flags (highest stakes — must be live + conflict-free):** on any contributing-session change
  (undo / edit / reject / assign), the patient's flag set is recomputed **from source** — the **union of
  all that patient's sessions' current kept flags** (kept = detected − user rejections). Conflict +
  duplicate resolution is delegated to the **safety-reconcile job** (D7) — a narrow, selection-only LLM
  step, *not* Job 4 and *not* free-generation. Removal (a rejection) is a **deterministic, instant**
  filter (no LLM). A rejection **follows its flag across a re-synthesis that rewords the text**: the
  reject endpoint keeps a rich `rejected_safety_flag_record` (kind + source captures) beside the plain
  key, so `kept` re-identifies the reworded flag (same kind + shared source capture) and drops it —
  a bare `kind|text` key alone could not survive rewording. On a **reassignment**, the wrong patient's
  flags are dropped and the new patient's synced at the one assignment choke point
  (`apply_active_patient_assignment`), which every path (staff, AI, capture-delete) routes through.
  The deterministic reconcile-apply layer (`apply_safety_reconciliation`) is hardened so a stale or
  cross-patient decision set can never lose a distinct allergy: an `ofKey` that doesn't resolve to a
  **visible flag on THIS patient** downgrades to keep, and a **mutual-duplicate cycle** keeps exactly
  one canonical flag visible instead of hiding every member.

### D7 — Safety-reconcile job (cross-visit dedup/supersede; selection-only, keys-out)

A small dedicated LLM job owns cross-visit safety reconciliation — decoupled from Job 4 (so it's *fresh*,
not lazy) and from synthesis generation (so it can't hallucinate). Properties:

- **Trigger:** only when synthesis **detects** safety content for a session (most visits have none → zero
  cost). Patient-scoped; fires on the session→patient projection.
- **Input = the user-CLEAN candidate set.** User actions are ground truth: rejected flags are removed
  **before** the LLM runs — it never sees, reasons over, or can re-surface a rejected item. (Rejected
  records persist in the DB — key in `rejected_safety_flags` + the full record in the immutable
  `report_version` — auditable / harvestable, never a candidate, never displayed.) This also avoids the
  "survivor points at a removed cluster head" bug.
- **Output = a status per candidate** (`keep` / `duplicate-of:<key>` / `superseded-by:<key>`) — **keys
  only**, minimizing output tokens (the real cost). **Biased to keep:** a *distinct* concept is never
  dropped (safety errs to inclusion); `superseded` items are **annotated, not deleted** ("previously
  flagged, superseded in a later visit"). A deterministic step collapses duplicate clusters + keeps singletons.
- **Selection, not generation:** clinical text stays verbatim from the candidates; the model only emits
  keys + statuses → no rewording, no invention.
- **Rejection needs no re-run:** removing a kept item is a deterministic filter; only *new detections*
  invoke the LLM.
- **New AI job ⇒ its own eval suite** (per the eval-gating rule): `safety_reconcile_eval.py` with
  dedup-merge, distinct-allergies-both-kept, supersede, and the critical **never-drop-a-distinct-allergy**
  guard; wired into `run_all.py`. Case list reviewed with the owner before wiring.
- **Frontend:** a `safety_reconcile: {state}` signal on the session/patient payload drives an animated
  "processing safety…" shimmer on the safety section while the job runs (distinct from the report's own
  updating state) — so on an already-assigned session the clinician sees safety is being reconciled.
- **Versioned/cached** like other artifacts: keyed by the clean candidate set, so it cache-hits (e.g. on
  undo returning to a prior set) and stays token-cheap.

> **Ground-truth invariant (extends D2):** user state (rejections, confirmations, opt-outs) is
> authoritative and applied **before** any AI step. The AI reconciles only the user-clean set and may
> never override or re-surface a user-decided item.

### D5 — Retention / GC: bounded ring + pins + content-addressing
Versioning everything grows unbounded, so:
- Keep a **bounded per-session ring** of recent `report_version`s (current + last N) for the fast
  **restore/redo** path; **GC** beyond it.
- This is safe because **middle-capture undo recomputes anyway** — losing an old cached version costs an
  occasional recompute, never correctness.
- **Pin** (never GC) any version referenced by a **verified/finalized** report.
- **Content-address** keys (hash of the ordered capture-version set) so identical sets share one stored
  version — natural storage dedup, and the mechanism behind undo's cache-hit.

### D6 — Storage shape: introduce the identity/version layer first, normalize entities later
Today treatments/flags/report are JSON in `extracted_metadata`, consumed across the A↔B synthesis
contract + backend + frontend. To avoid a big-bang refactor: first add a **`report_versions` store**
(keyed by the ordered capture-version set) holding **today's JSON shapes** + the user-state overlay
reference; ship undo on it. **Normalize** entities (treatments/flags → versioned rows) **incrementally**
afterward. The A↔B contract stays JSON over the wire; only persistence evolves.

## Undo as the first consumer
One **removal operation** that fully de-effects (UX: the Sources drawer in
[ux/screens/capture.md](../ux/screens/capture.md)):
- **Last capture** → input set returns to a previously-seen set → **cache-hit restore** of the prior
  `report_version` (deterministic, no LLM) + re-derive patient projections.
- **Middle capture** → no prior version equals "all-except-C" → **recompute** (one LLM pass), with the
  user-state overlay re-applied.
- **Patient action revert** (spurious AI-created patient) is part of the operation.
- "**Undo**" = the one-tap shortcut for the last capture; per-capture "**Delete**" = the same operation
  for any capture — identical effect.

## Permissions
Removal/edit is gated at a **single policy-resolution point** (undo v1 default: owner-only for the
destructive de-effect). A tenant **edit-policy** (strict = owner-only · standard = owner+admin · open =
any staff) + its settings UI + non-owner-edit attribution markers are a **fast-follow**, not a blocker.

## Eval gating
Synthesis caching/versioning **is an AI-job change**, so per the eval-gating rule it must run
`apps/ai_engine/eval/run_all.py` green; the determinism work (cache-hit restore) should add targeted
cases proving "undo restores the exact prior structured artifacts" (consult the owner on new suites).

## Phased plan
1. **Version + identity layer** (`report_versions` keyed by ordered capture-version set) + the
   **user-state overlay** split (D2/D6). No behavior change yet — shadow the current JSON.
2. **Undo on cache-hit restore** for the last capture + **patient-action revert** + the **owner policy
   point** (undo v1).
3. **Middle-capture recompute** path + the patient-projection recompute-from-source (D4) + staleness
   propagation to patient memory (D3).
4. **GC/retention** (D5), **incremental entity normalization** (D6), and the **3-mode edit-policy
   setting + UI** (fast-follow).

## Open questions
1. ~~`report_versions` home — dedicated table vs a normalized extension of today's
   `processed_versions` ring?~~ **Answered:** a dedicated table, `session_report_versions`
   (queryability + pins).
2. Capture-level versioning depth — do we retain every transcription edit as a `capture_version`, or
   only the current + last (for capture-text undo)? (Affects D5 ring sizing.)
