# Intelligence Layer — v1 Design Contract

Status: **design + largely implemented** (assignment/reassignment, out-of-context, near-match,
tiering, and the Pro live report have shipped — see the DONE markers in
[intelligence-layer-stories.md](intelligence-layer-stories.md)). This is the single source of
truth for how the AI engine, backend, and frontend agree on capture *intelligence*: what the
model emits, how the backend applies it, and how the frontend renders the effect. It replaces today's
implicit coupling, where the AI emitted extracted identity and the backend silently chose
whether to apply it (the root of the "audio said reassign but nothing changed" bug — see
[ai_engine/processing.md](ai_engine/processing.md) "If a session already has a DB-owned
patient assignment, generated identity is skipped … and cannot override it").

Implementation is sliced into vertical, demoable stories in
[intelligence-layer-stories.md](intelligence-layer-stories.md).

## 1. Scope

In: **intent-aware capture processing** for three intents — **assignment/reassignment,
append, out-of-context**. Apply-then-notify (no confirmation modals); every effect is
non-destructive, attributed to its capture, and reversible.

Out (v1 non-goals): the **`edit`** intent (mutating structured-report fields) and the
field-level provenance / jump-to-section it requires; lab integrations; multi-template
reports.

## 2. Entity model — Patient is universal; the *encounter* generalizes

Every vertical still has a **`Patient`** (the person), so Patient is **not** abstracted —
it stays the assignment target, and `patient_information` + the patient-keyed timeline stay
correct as-is. What varies by vertical is the **report-required work-unit**: a clinic
**Session**, a radiology **Study**, a pathology **Case**. These are one generic
**`Encounter`** (`Patient 1—* Encounter 1—* Capture`, one `Report` per Encounter),
distinguished by a `tenant.vertical` (+ an `encounter.type`) and specialized by a per-type
`attributes` JSONB (radiology: accession/modality/body_part; pathology: specimen_id/stain).
v1 ships clinics only, so the Encounter is implemented as today's **`Session`**; the literal
`Session → Encounter` rename and per-vertical fields land with the second vertical. Until
then *encounter* == `Session`, and "assignment" everywhere means *attach this encounter (and
its captures) to a `Patient`*. Keep the physical name generic and localize the label
("Session"/"Study"/"Case") at the presentation edge. Do **not** hardcode new clinic-only
assumptions into the apply layer.

## 3. Tiers (MVP ships both)

A new tenant-level `tier` (`basic` | `pro`) gates the pipeline. The intent **schema is the
same** for both tiers; tier controls which fields the model is asked to populate and which
the backend applies.

| Capability | Basic | Pro |
| --- | --- | --- |
| Audio transcription | ✅ | ✅ |
| Out-of-context flag | ✅ | ✅ |
| Manual/assisted subject assignment | ✅ | ✅ |
| **AI auto-assignment / reassignment / match / create** | ❌ (manual only) | ✅ |
| Image captions, text decoration | ❌ | ✅ |
| Live report | chronological captures + transcripts (Apple-Notes feel) | synthesized, refined per capture |

`append` is the default chronological behavior in Basic (no signal needed); the explicit
`append` intent is only consumed by Pro report refinement.

**Language preferences (tenant-level).** `tenant.transcription_language` (default `auto`) and
`tenant.report_language` (NULL = follow the report template's default) are settable by staff
(`PATCH /tenant/settings`, surfaced on the `TenantProfile`). Transcription is told to transcribe
**verbatim in the spoken language and original script — never translate or romanize** (auto), or
in the chosen language's native script; this is critical because a romanized Persian transcript
(e.g. "Bimar ro avaz kon…") breaks name matching, so an explicit reassignment silently fails.
The preference rides on `transcriptionContext.preferredLanguage`; report language rides on the
session-processing context (`reportLanguage`).

**Match strictness (tenant-level).** `tenant.match_strictness` (`strict` | `balanced` | `lenient`,
default `strict`) moves the single-candidate auto-apply line for **fuzzy** name matches only
(§5.4). `strict` = deterministic matches only (preserves prior behavior); `balanced`/`lenient` =
also auto-apply a single high-confidence fuzzy match with an **explicit** reassignment instruction,
at a high/lower threshold. The national-ID conflict guard and ambiguous-multi-candidate routing
apply at every level. Settable via `PATCH /tenant/settings` (`matchStrictness`), surfaced on the
`TenantProfile`. Lives on the B4 Settings page (temporarily in the Shell menu).

## 4. AI output schema — `2026-06-03.capture-intelligence.v1`

Extends the current structured-transcription output. **`transcript` is required;
everything else is nullable** so a malformed/uncertain intent never nukes a usable
transcript. Use the gateway's structured-output schema *and* keep a thin normalization
layer (the dev gateway is Gemini-via-OpenAI-compat — strict `json_schema` support is
partial, especially with audio input).

```jsonc
{
  "schemaVersion": "2026-06-03.capture-intelligence.v1",
  "transcript": "string",                       // required
  "language": "fa|en|mixed|unknown",
  "clinical_summary": "string|null",
  "uncertainties": ["string"],
  "patient_information": { /* existing identity fields */ } | null,   // subject identity
  "intents": {                                  // null in Basic; populated in Pro
    "assignment":      { "present": true, "basis": "explicit|implicit", "confidence": 0.0, "evidence": "string" } | null,
    "append":          { "present": true, "confidence": 0.0 } | null,
    "out_of_context":  { "present": true, "confidence": 0.0, "reason": "string" } | null
  } | null
}
```

`basis` is the key new signal: `explicit` = the speaker instructed a (re)assignment
("change the patient to …"); `implicit` = a subject was merely mentioned.

## 5. Backend apply semantics (per intent, tier-gated)

### Assignment (Pro; Basic = manual resolver only)
Reuses the existing event-sourced timeline (`patient_assignment_timeline.py`):
`append_patient_assignment_event` → `apply_active_patient_assignment` already does
**latest-valid-event-wins**, recomputes `session.patient_id`, and **drops events whose
capture was deleted** (this *is* undo). The fix is to stop suppressing the append:

1. **First identity wins (any basis).** With no patient yet (`session.patient_id is None`),
   explicitly-extracted identity is applied: deterministic `matched` → assign; `no_match`
   with usable identity → **create + assign** (flagged needs-review); ambiguous → human
   resolver. Intent basis is irrelevant for the first assignment.
2. **Once assigned, only an explicit instruction overrides.** When a patient is already
   assigned (by staff or matching), a later capture changes it **only if
   `intents.assignment.basis == "explicit"`** (a clear re/assignment or correction
   instruction) — regardless of `verified` status — appended as a timeline event
   (latest-wins) with an **Undo** chip. Replaces the hard gate in `complete_worker_job`.
3. **Implicit mention on an assigned visit → suggest, don't apply.** If a later capture only
   *mentions* a patient (`basis == "implicit"`, or no explicit intent), the assignment is
   **not added**; the backend runs matching and stores an **actionable suggestion**
   (`status: "suggested_reassignment"`) surfaced as a capture chip + Needs-input item that
   the user can apply in one tap. Nothing reassigns silently.
4. Auto-apply **only on deterministic `matched`/`no_match`** by default; `possible_match`/ambiguous
   routes to the human resolver, even in Pro. **Exception (H3/H4):** a single high-confidence
   **fuzzy** `possible_match` auto-applies (reversible, with notify) when `tenant.match_strictness`
   is `balanced`/`lenient` **and** the assignment basis is `explicit` — never on an implicit
   mention, a tie, or a national-ID conflict. Otherwise it surfaces as a partial-match
   **suggestion** on the capture card (the H4 quick-action surface: Keep match / Create new
   instead (editable form) / Choose another — see
   [redesign-capture-surface.md](ux/redesign-capture-surface.md)). **Precedence (D1):** a staff
   assignment is overridden only by another staff action or an explicit-basis AI capture.

Matching reuses the unchanged ladder (national_id → phone/email → exact alias → fuzzy →
LLM-rank); the timeline (`patient_assignment_timeline.py`) already does latest-valid-wins +
undo-by-capture-deletion. All applies are non-destructive timeline appends → capture chip +
undo.

### Append
Basic: no-op (chronological default). Pro: the capture is folded into the Live-report
refinement job; recorded as a `report_contribution` effect on the capture.

### Out-of-context (both tiers)
Store an `out_of_context` effect on the capture. The capture is **kept**, **excluded from
the report** (Pro) and **visually dimmed** (both); a one-tap "actually relevant"
reclassify clears it. Never auto-deleted.

## 6. Capture effects & attribution

Generalizes today's `patient_action_badges`. Each capture carries an `effects` list in its
metadata; the frontend renders chips from it:

```jsonc
"effects": [
  { "type": "assignment", "action": "matched|created|reassigned", "subjectId": "…",
    "displayName": "…", "basis": "explicit|implicit", "undoable": true },
  { "type": "suggested_assignment", "action": "reassign|create", "subjectId": "…",
    "displayName": "…", "matchedName": "…", "spokenName": "…",
    "appliedAutomatically": false },   // partial match, or implicit mention on assigned visit;
                                       // matchedName vs spokenName drives "Matched X · you said Y"
  { "type": "out_of_context", "confidence": 0.0, "reason": "…" },
  { "type": "report_contribution", "status": "added|updating|pending" }   // Pro
]
```

## 7. Frontend render model

See [ux/redesign-capture-surface.md](ux/redesign-capture-surface.md) for the full surface
spec; the contract-level points:

- Tabs renamed **Captures / Live report**, **centered in the Clinical report header**
  (desktop). The manual **Generate button is removed**; the Live report is always present.
- Capture cards keep **type icons** and an inline **Edit** on each generated text block
  (transcript/caption/decorated text) — editing the capture's text, distinct from the
  deferred report-`edit` intent.
- Each capture shows **effect chips** (a capture may carry several — e.g.
  `created_and_assigned`): "Patient (re)assigned → N · Undo", "New patient + assigned",
  "Added to report", "Out of context" (dimmed), plus calm processing/offline states. A
  superseded AI-created+assigned capture routes its now-unused patient to **Needs
  input/review** rather than orphaning it. "Patient assigned" already exists; this
  generalizes it.
- **Suggested reassignment:** an implicit patient mention on an already-assigned visit is
  **not applied** — it shows a `Suggested: reassign to N · Apply / Dismiss` chip (and a
  Needs-input item) the user can act on in one tap.
- **Live report is a document, both tiers:** a clinic + patient header from template/DB
  (not AI). **Basic** = chronological captures + transcripts + images. **Pro** = a
  **template-driven, synthesized** report (no per-line timestamps), **regenerated by an AI
  job as each capture lands**. The report **template** is the fixed aesthetic default today
  and **user-uploadable later** (radiology/pathology); its name lives in the report meta
  strip, not the patient block.
- **Undo** = remove the capture's contribution and recompute (assignment: drop its timeline
  event; reuse capture-deletion-removes-event). Never destructive to the raw capture.
- "Verify" becomes a calm confirm on the live report, not a post-generate gate.

## 8. Offline, AI-out, storage durability

- **Capture durability is the sacred guarantee:** persist locally ("Saved on this device")
  before any network. The **Captures view is the always-available fallback** when network
  or AI is down — only enrichment (transcripts, captions, refined report) lags, shown as a
  quiet inline state, never an error or modal.
- **AI-out is silent and self-healing** via the existing durable job-retry/recovery path.
- **The only hard-stop is durable storage full** (can't guarantee a new capture survives):
  warn at ~80% via `navigator.storage.estimate()`, **guard before a long recording**
  rather than failing after, offer an **export** escape hatch for queued captures, and
  request **`navigator.storage.persist()`** (Safari/iOS can evict IndexedDB — fatal for a
  never-lose-data promise).

## 9. Concrete changes vs. current implementation

1. AI engine: add `intents` to the transcription prompt + output schema (Pro); adopt
   gateway structured output + thin normalization.
2. Backend: replace the assignment-suppression gate in `ai_jobs.complete_worker_job`
   ([apps/backend/app/services/ai_jobs.py](apps/backend/app/services/ai_jobs.py)) with the
   §5 override rule; generalize `patient_action_badges` → `effects`; add `out_of_context`
   handling; add tenant `tier` + tier-aware gating.
3. Frontend: Captures/Live-report tabs, remove Generate, render effect chips + undo,
   out-of-context card state, offline/storage durability.
4. Patient IA: add **Unassign** to the resolver; dedicated patient detail view/edit;
   unified creation (see UX docs, separate change).

## 10. Open decisions

- **D1 — staff vs. AI precedence** (§5.3): recommended default above; confirm.
- **D2 — tier granularity:** tenant-level `tier` (recommended) vs. per-user.
- **D3 — Basic prompt cost:** Basic asks the model only for `transcript` + `out_of_context`
  (skips assignment/append) to stay cheap; confirm.
