# Pipeline versioning (capture → report → patient memory)

> **Goal.** Make the AI pipeline an **incremental, memoized computation over versioned inputs**, so that
> (1) **undo/redo restore prior state deterministically** instead of re-generating it (no "wrong
> entries"), (2) **LLM tokens are saved** by reusing a stored output whenever its exact input set
> recurs, and (3) **everything stays consistent** — the rendered report, its structured entities
> (treatments, safety flags, aftercare), and the cross-visit patient projections are always a function
> of the current inputs. [Capture undo](../ux/redesign-capture-undo.md) is the first consumer.

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
  (undo / edit / reject / assign), recompute `Patient.safety_flags` from the **union of all that
  patient's sessions' current kept flags** (kept = detected − rejected). Dedup by stable key; most-recent
  statement wins per concept. True clinical contradiction reconciliation (allergic-vs-tolerated) is out
  of scope for v1 — baseline is union + dedup (safety errs to inclusion); smarter reconciliation is
  later, in the AI memory layer.

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
One **removal operation** that fully de-effects (see [redesign-capture-undo.md](../ux/redesign-capture-undo.md)):
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
1. `report_versions` home — dedicated table vs a normalized extension of today's `processed_versions`
   ring? (Leaning table for queryability + pins; revisit once the overlay shape is fixed.)
2. Capture-level versioning depth — do we retain every transcription edit as a `capture_version`, or
   only the current + last (for capture-text undo)? (Affects D5 ring sizing.)
