# Intelligence Layer — v1 Design Contract

Status: **shipped** (assignment/reassignment, out-of-context, near-match, tiering, and the Pro
live report are all built). This is the single source of
truth for how the AI engine, backend, and frontend agree on capture *intelligence*: what the
model emits, how the backend applies it, and how the frontend renders the effect. It replaces today's
implicit coupling, where the AI emitted extracted identity and the backend silently chose
whether to apply it — the root of the historical "audio said reassign but nothing changed" bug,
where a DB-owned assignment unconditionally suppressed extracted identity.

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

## 3. Tiers → capabilities

A tenant's `(vertical, tier)` resolves to a **capability set**; features gate on membership in that
set, never on `tier` directly. The composition per vertical lives in [spines.md §3](spines.md), and
the code truth is `apps/backend/app/services/capabilities.py`: aesthetics **Basic is zero-AI** (the
deterministic floor — structured capture, manual assignment, search; no transcription, no matching,
no out-of-context, no capture AI job at all — AES-101), aesthetics **Pro** gets the full set
(`transcription`, `image_caption`, `patient_matching`, `out_of_context`, `cross_visit_synthesis`,
`live_report_synthesis`, `post_session_qa`), and therapy is a single plan with the full set.

What §5 needs from this: the intent **schema is the same** wherever the pipeline runs, and the
per-intent apply rules below are tier-independent — but each behavior exists **only when the
tenant's capability set grants it** (`patient_matching` for assignment/reassignment/suggestions,
`out_of_context` for the OOC effect, `image_caption` for captions, `live_report_synthesis` for the
synthesized report). A capture for a tenant with no capture-AI capability is saved
deterministically, with no AI job and no `processing` state.

**The live report is deterministic-first, synthesis-refined.** Once the capture chain is idle the
backend rebuilds a deterministic report synchronously, so a report is always present and current.
Tenants with `live_report_synthesis` then get the single-pass synthesis job (`session_organize`)
that overwrites it with the structured per-visit report + extracted `treatments[]`; without it (or
without a gateway) the deterministic report stands. See
[ai_engine/processing.md](ai_engine/processing.md) "Session synthesis".

**Per-task models (live).** Each AI task (transcription, caption, report synthesis, patient memory,
Q&A) can run on its own model. The selection is live: per-task overrides are stored in
`app_config.ai_models` and edited via `GET`/`PUT /api/v1/ai-config/models` (takes effect on the next
request; worker env is the fallback, gateway URL/key stay env-only). Notes are a pure passthrough
(no AI), so there is no note model. See [ai_engine/processing.md](ai_engine/processing.md)
"Per-task models".

**Completion is auto-derived (no manual "verify").** A session is **complete** when its captures are
processed, a patient is assigned, and the report is current (not stale) for the latest capture. This
replaces the manual *Verify report* gate: `complete` is computed and surfaced on the session payload
(and as the patient-memory `complete` indicator); editing/adding a capture marks the report stale and
flips the session back to incomplete until it regenerates.

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

### Assignment (both tiers)
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
   instruction) — regardless of prior confirmation — appended as a timeline event
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
   [ux/screens/capture.md](ux/screens/capture.md) "Partial-match resolution"). **Precedence (D1):** a staff
   assignment is overridden only by another staff action or an explicit-basis AI capture.

Matching reuses the unchanged ladder (national_id → phone/email → exact alias → fuzzy →
LLM-rank); **fuzzy is token-aware**, so a transcription that mentions only a first or last
name still surfaces the full-named patient as a `possible_match` for review (and vice-versa,
when the patient was stored under a partial name). The timeline
(`patient_assignment_timeline.py`) already does latest-valid-wins +
undo-by-capture-deletion. All applies are non-destructive timeline appends → capture chip +
undo.

#### Identity corrections, detach & the never-silent invariant (E1)

The whole lattice above resolves in one place — `_resolve_capture_identity` in `worker.py` — under
three structural invariants. **INV-SILENT: a confident detection or an explicit instruction always
ends in exactly one of an applied effect, a visible suggestion, or a visible "couldn't act" notice**
— never success-shaped silence (a completion-time backstop asserts it, and a unit-level lattice test
covers every cell). The added decision kinds:

5. **Name correction, not echo (Fix 1).** An assignment that resolves to the *currently-assigned*
   patient but whose spoken name materially differs from the stored name is a **name correction**, not
   an echo. Explicit basis + a role permitted to reassign + an AI-created *unverified* patient →
   **rename in place** (`decision: "name_corrected"`, before→after harvested via the feedback helpers,
   never editing `feedback.py`). Otherwise → a one-tap **`suggested_name_correction`** chip. A genuine
   echo (spoken name ≈ stored name) stays silent.
6. **Dead-zone create+assign (Fix 7).** On an *unassigned* visit whose detected identity clears no
   assign/suggest threshold (the 0.762 `possible_match` dead zone below `NEAR_MATCH_SUGGEST_THRESHOLD`
   0.78), treat as `no_match` → **create + assign** the spoken patient (first-identity-wins), keeping
   the closest look-alike as an informational `similarExisting` note with a one-tap use-existing escape.
   The 0.78 floor gates candidate *promotion*, never whether a resolution path exists.
7. **AI-create duplicate guard (A-F16).** AI creation runs the AES-205 duplicate guard; a strong hit
   (id/phone/email/exact-name) **suggests use-existing** (`duplicateGuard: true`) instead of splitting
   the record.
8. **National-ID name cross-check (A-F5).** A national-ID hit whose *also-spoken* name is materially
   inconsistent with the ID-matched patient is **demoted to `possible_match`** with a mismatch risk
   (never auto-applied at any strictness) — one dictated-digit ASR error can no longer silently write
   the wrong chart.
9. **Detach / negation (A-F9).** `intents.detach.present` (e.g. "wrong patient, remove her") with no
   replacement identity → a **`suggested_unassign`** chip (never a silent no-op; unassign is destructive
   so it is only ever suggested).
10. **Explicit-but-no-effect (A-F12).** An explicit instruction that matched/created nothing →
    an actionable **`assignment_no_effect`** ("couldn't apply — assign manually") notice carrying the
    spoken identity.
11. **Inert recovered assignment (A-F7).** A recovered older capture whose appended event does not
    become the active assignment surfaces an **`inertAssignment`** conflict chip instead of nothing.

**INV-LOCK:** every completion holds `SELECT … FOR UPDATE` on the session row so two capture
completions can't clobber each other's timeline event; capture dispatch is routed through the ordered
`dispatch_next_session_capture` (never straight past a running sibling).
**INV-INVALIDATE:** marking a capture out-of-context or editing its transcript re-evaluates the
assignment it drove (see Out-of-context below and `captures.update_capture`).

### Append
Basic: no-op (chronological default). Pro: the capture is folded into the Live-report
refinement job; recorded as a `report_contribution` effect on the capture.

### Captions (Pro)
Image captions (photo) are real Pro enrichment produced by the AI engine through the configured
multimodal gateway, then written to the capture's `caption` metadata. The gate lives at the
worker-payload boundary: the backend attaches an `enrichmentContext` to a photo job **only when the
tenant has the `image_caption` capability**, so Basic — and any gateway-less or QA-fixture capture —
keeps a blank/deterministic caption. Captions describe only what is clinically visible, in the
source language/native script (no romanization). Notes carry **no enrichment**: `text_capture_process`
is a pure passthrough (decoration removed — report synthesis reads the raw note text). See
[ai_engine/processing.md](ai_engine/processing.md) "Photo — Pro caption + enrichment attributes".

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

See [ux/screens/capture.md](ux/screens/capture.md) for the full surface spec; the
contract-level points:

- Tabs renamed **Captures / Live report**, **centered in the Clinical report header**
  (desktop). The manual **Generate button is removed**; the Live report is always present.
- Capture cards keep **type icons** and an inline **Edit** on each generated text block
  (transcript/caption) — editing the capture's text, distinct from the report-`edit` intent, which
  ships as a **human-authored treatment overlay** (AES-1102, no AI — see
  [ux/screens/session-review.md](ux/screens/session-review.md)).
- Each capture shows **effect chips** (a capture may carry several — e.g.
  `created_and_assigned`): "Patient (re)assigned → N · Undo", "New patient + assigned",
  "Added to report", "Out of context" (dimmed), plus calm processing/offline states. A
  superseded AI-created+assigned capture routes its now-unused patient to **Needs
  input/review** rather than orphaning it. "Patient assigned" already exists; this
  generalizes it.
- **Suggested reassignment:** an implicit patient mention on an already-assigned visit is
  **not applied** — it shows a `Suggested: reassign to N · Apply / Dismiss` chip (and a
  Needs-input item) the user can act on in one tap. The E1 correction chips
  (`suggested_name_correction`, `suggested_unassign`) likewise **apply in one tap** on the resolver —
  rename-in-place / unassign via their dedicated endpoints (see
  [ux/screens/capture.md](ux/screens/capture.md) "Added chip kinds").
- **Live report is a document, both tiers:** a clinic + patient header from template/DB
  (not AI). **Basic** = chronological captures + transcripts + images. **Pro** = the synthesized
  per-visit report: a deterministic baseline rebuilt as each capture lands, overwritten by the
  `session_organize` synthesis job (fixed sections + extracted `treatments[]` — see
  [ai_engine/processing.md](ai_engine/processing.md) "Session synthesis"). The
  report **template** is the fixed aesthetic default today and **user-uploadable later**
  (radiology/pathology); its name lives in the report meta strip, not the patient block.
- **Undo** = remove the capture's contribution and recompute (assignment: drop its timeline
  event; reuse capture-deletion-removes-event). Never destructive to the raw capture.
- **No manual "Verify report"** — a session shows a calm, auto-derived **Complete** state
  (captures processed + patient assigned + report current) instead of a verify gate.

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
   ([apps/backend/app/services/ai_jobs/worker.py](../apps/backend/app/services/ai_jobs/worker.py)) with the
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
