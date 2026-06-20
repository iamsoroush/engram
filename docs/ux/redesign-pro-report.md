# Pro Report — polished rendering (clinical + shareable)

> **Status: design, for product-owner review (not built).** Story C of the Pro capture-intelligence
> wave ([capture-intelligence-design.md §Handoff stories](../ai_engine/capture-intelligence-design.md)).
> Designs the *rendering* of the **one** synthesized Pro report — used **both** as the in-app clinical
> report **and** the shareable patient artifact. Closed decision it implements: **one report, no
> separate patient projection** ([capture-intelligence-design.md Out-of-scope](../ai_engine/capture-intelligence-design.md)).
>
> Aesthetics-first, **vertical-agnostic** via the domain descriptor (the same rendering serves
> therapy/derm later; nothing here is aesthetics-coded except sample copy).
>
> **Grounded in the real contract** — every field rendered below comes from the synthesis output
> (`2026-06-15.session-synthesis-output.v1`) and the share payload; **no invented fields.**
> Reuses the built design system (tokens + components) from
> [`aesthetics-report.html`](../../apps/frontend/design-prototypes/aesthetics-report.html) +
> [`aesthetics-patient-surface.html`](../../apps/frontend/design-prototypes/aesthetics-patient-surface.html).
>
> **Prototype:** [`aesthetics-pro-report.html`](../../apps/frontend/design-prototypes/aesthetics-pro-report.html)
> — both renderings, the organizing/updating state, the treatment table, and a before/after slider,
> with realistic Persian + English content.
>
> **Reads against:** the A↔B contract ([capture-intelligence-design.md](../ai_engine/capture-intelligence-design.md)),
> the fixed sections + patient-surface contract ([redesign-foundation.md §3, §4](redesign-foundation.md)),
> the Pro report + share stories ([redesign-aesthetics.md §4, §6](redesign-aesthetics.md)),
> [redesign-capture-surface.md](redesign-capture-surface.md), [design-principles.md](../design-principles.md),
> and [states.md](states.md). **Scope: rendering only** — this re-renders the existing report/share data
> cleanly. It does **not** change capture, the synthesis pipeline, or the share contract.

---

## 1 · What this is (and isn't)

There is **one** synthesized report per visit. It is rendered in **two surfaces** of the **same data**:

1. **Clinical (in-app)** — the doctor's working document. Every section, every extracted treatment,
   all confidence/uncertainty surfacing, full before/after media, both the *complete* and *updating*
   affordances. This supersedes the current Pro `LiveReport` view
   ([LiveReport.tsx](../../apps/frontend/src/features/capture/components/LiveReport.tsx)).
2. **Shareable (patient)** — the public `/share/{token}` page rendering of the **same report**,
   read-only, **curated** by the doctor, with clinic internals **withheld** per
   [foundation §4](redesign-foundation.md). This supersedes the current
   [PatientSharePage](../../apps/frontend/src/features/patient-surface/PatientSharePage.tsx).

**It isn't:** a new pipeline, a new contract, a redesign of capture, or a second "patient projection."
The patient page renders a *subset* of the same report the doctor sees — the difference is **curation +
withholding**, never a different document. *Why:* "one report, no separate patient projection" is a
closed decision — two documents diverge, double the maintenance, and erode trust ("which one is real?").

**Vertical-agnostic.** Section *titles* come from the synthesis output (`sections[].title`, which the
LLM writes in the report language for the domain). The rendering keys off the **fixed section `id`s**,
never hard-coded English titles, so therapy/derm reports drop in unchanged.

---

## 2 · Clinical rendering (in-app)

### 2.1 The document shell

Reuses the existing report-card chrome ([redesign-capture-surface.md B2](redesign-capture-surface.md)):
a **Clinical report** card with the `Pro` tier badge, the clinic doc-header (logo / name / address from
template+DB, **not** AI), the patient-info block (from DB), then a **meta strip** and the body.

- **Meta strip** carries the *report's basis*, the single most important trust signal: the
  **Complete / Updating** state (§2.6) + `Generated from N captures · M set aside` (M = out-of-context),
  + the template name & `Change` affordance (right-aligned). All already in the built `report-meta-strip`
  — this design tightens its visual hierarchy, nothing new in the data.
- **No Generate button, no verify gate** — the report is always live
  ([redesign-capture-surface.md](redesign-capture-surface.md)).

*Why a fixed shell:* clinic + patient identity must read as a real clinical document (the thing Apple
Notes can't make — [foundation §3 Basic 6](redesign-foundation.md)); only the *body* is AI.

### 2.2 The fixed sections (rendered from `sections[]`)

Rendered **in contract order**, each from `sections[].blocks[]`. The renderer maps by the **fixed `id`**,
not the title:

| `id` | Renders as | Notes |
| --- | --- | --- |
| `visit-summary` | lead paragraph (slightly larger) | 1–2 lines; mirrors `summary` |
| `concern-goals` | paragraph(s) | patient's words/goals |
| `assessment` | paragraph(s) | clinician findings |
| `treatment-performed` | **the treatment table (§2.3)** | the prose blocks are the *mirror*; we render the **structured `treatments[]`** as the primary surface, with the prose as a collapsible "in words" view |
| `media` | **before/after media (§2.4)** | `image` blocks → resolved files |
| `plan-followup` | paragraph(s) | next steps |
| `aftercare` | checklist | line-split into ticked items (same treatment as the share page's `ps-care`) |

- **Empty sections are dropped** (the LLM leaves a section's blocks empty when captures don't support
  it — "leave null rather than guess"). A scannable report shows only what's grounded.
- **Per-line RTL** ([redesign-capture-surface.md](redesign-capture-surface.md)): each block/line renders
  RTL when predominantly Persian/Arabic, LTR otherwise — **mixed-language is per-line, not per-report**,
  so a Farsi report with an English brand name stays correct.

*Why structured-table-first for `treatment-performed`:* the table is the queryable truth
(`treatments[]` → `extracted_metadata.treatments`) and is what the doctor scans for "what did I give";
prose is the readable mirror but can't carry confidence/lot/carry-forward chips cleanly. We render
both — table primary, prose one tap away — so nothing the LLM wrote is hidden.

### 2.3 Treatment table — the clinical core

The signature surface. One row per `TreatmentItem`, columns from the **stable core**:

`Area · Product · Brand · Units · Lot` — i.e. `area`, `product`, `brand`, the **quantity** column,
and `lot`.

**Quantities are VERBATIM.** The units cell shows **`quantityText`** (the original dictated string, in
its original script — `۲۰ واحد`, `2 cc`, `0.8 ml`) when present, falling back to `quantity + unit`.
*Why:* the contract mandates verbatim quantities/brands; a doctor must see *exactly what they said*, not
a re-rendered number — that's the audit trail and the trust anchor.

**Per-row chips** (the uncertainty surfacing, from the item's own fields):

- **`carried forward · confirm`** (amber) when `carriedForward: true` — "same as last time", cited to
  the prior visit, **lower confidence by design**. Never silently materialized. Tappable → confirm
  surface (writes back; this is also a Needs-input item per the
  [uncertainty contract](../ai_engine/capture-intelligence-design.md)).
- **`needs confirm`** (amber) when `supersedesCaptureId` is set on an **ambiguous** correction, or the
  item appears in top-level `uncertainties[]` — "AI unsure → tell the human"
  ([capture-intelligence-design.md §Cross-cutting](../ai_engine/capture-intelligence-design.md)).
- **low-confidence** treatment (`confidence` below the per-job threshold) → the **whole row is tinted**
  + a small `low confidence` marker; tap reveals `evidence` (the grounding snippet) + the source capture.
- **superseded** corrections: the *replaced* value shows struck-through with a `was …` micro-note
  (auditable/undoable, mirrors the capture-surface `kept for review` treatment) so a correction is
  visible, not silent.

**Missing-but-expected lot** (e.g. an injectable with no `lot`) shows a quiet `lot?` placeholder, not a
blank — it's a known uncertainty the contract raises (`missing-but-expected lot`).

Each row links to its `sourceCaptureIds` ("from your 14:08 dictation") so every clinical claim is
traceable to a capture. *Why:* the report's authority is that **nothing is invented** — one tap proves it.

**`attributes`** (open map: needleGauge, depth, device, sessions…) render as a **secondary line under
the row** (`23G · 2mm depth`) — present when the LLM extracted them, absent otherwise. Open map → render
generically (key·value), never a fixed schema, so new attributes appear without a code change.

### 2.4 Before/after media — side-by-side + slider compare

From the `media` section's `image` blocks (each `{captureId, caption}`), resolved to files
(`render_report_body_markdown` → file endpoint; **every `captureId` validated against the session,
unknowns dropped** — the contract's assembly rule).

- **Default: side-by-side** before/after pair with captions (the AI caption) beneath each.
- **Compare: a slider** (drag handle) overlays after-over-before for aligned progress reading — the
  aesthetics signature ([redesign-aesthetics.md §3.1](redesign-aesthetics.md): "the aligned slider
  compare"). Reversible; a small toggle switches side-by-side ⇄ slider.
- Unpaired/extra photos render below as a simple captioned grid.
- Media that fails to load degrades to a labelled placeholder (never a broken image) — matches the
  share page's `failed` state.

*Why both modes:* side-by-side is honest and scannable; the slider is the delight that sells the
before/after story to the patient — and the doctor curates from the *same* control they'll share.

*Pairing source:* the synthesis/caption job assembles before/after pairs (region/phase pairing is a
deterministic backend step over caption attributes —
[capture-intelligence-design.md Job 2](../ai_engine/capture-intelligence-design.md)). The rendering
**consumes** pairs; it does not pair. If only singles exist, it shows singles — no fabricated pairs.

### 2.5 Source / uncertainty surfacing (cross-cutting)

The report never hides "the AI is unsure." Three calm levels, escalating only as needed
([design-principles §6, §7](../design-principles.md), [states.md](states.md)):

1. **Inline, per item** — the row chips above (low-confidence tint, carry-forward, needs-confirm).
2. **A report-level "to confirm" affordance** — when `uncertainties[]` is non-empty, a quiet summary
   pill in the meta strip: `2 items to confirm` → scrolls/expands to the flagged rows. *Not a blocker.*
3. **Needs-input** — the items that need a *decision* (ambiguous correction, carried-forward dose)
   already route to the existing Needs-input surface via the backend `needsReview` effect
   ([states.md Needs-input](states.md)); the report just shows the chip and the resolver opens the
   smallest decision. The report itself is never a Needs-input destination
   ([states.md](states.md): "must not use the active session page as the primary destination").

*Why three levels:* most uncertainty is glanceable (a chip); some warrants a nudge (the pill); only a
real decision interrupts. This honors "warnings over blocking."

### 2.6 The states — Organizing / Updating / Complete

The calm assistant language ([states.md](states.md)). **The baseline report is always present** — the
deterministic grouped report runs first and stands until synthesis overwrites it
([capture-intelligence-design.md Job 3](../ai_engine/capture-intelligence-design.md)), so there is
**never a takeover/blank state**.

- **Organizing with AI — updates shortly.** When `session_organize` is running over fresh captures, the
  meta strip shows a quiet `Organizing with AI · updates shortly` line with a soft pulse — and **the
  current report stays fully visible and readable underneath** ([states.md Loading](states.md):
  "Loading should not replace the report … when saved content is already available"). Not a spinner over
  the document; a status on the meta strip. *Why:* enrichment lag is a quiet state, never an error or a
  takeover ([capture-intelligence-design.md Hard constraints](../ai_engine/capture-intelligence-design.md)).
- **Updating** — when new captures have landed but aren't yet folded in, the freshness line reads
  `Updating · N of M captures not yet in this report` (already in the built `report-freshness`), so the
  doctor knows the basis. Sections that *did* change get a brief, subtle `updated` tick;
  unchanged prose is byte-stable (the contract's update discipline keeps it from churning).
- **Complete** — once captures are processed, a patient is assigned, and the report reflects every
  in-context capture: the green `Complete` badge + `Reflects all N captures · M set aside`. Auto-derived,
  no manual verify.
- **Offline / AI-unavailable** — silent and self-healing ([states.md Offline](states.md)): the
  deterministic baseline shows, with `Organizing when available`; no retry buttons, no failure labels.
  Basic/gateway-less = the deterministic report stands, `treatments[]` empty — and **the Pro rendering
  must never break on a deterministic-only report** (it degrades to sections-only, no table).

### 2.7 RTL / Persian / mixed-language

- **Per-line direction** everywhere (§2.2) — sections, table cells, captions, chips. A Farsi report with
  `Dysport` and `D-4471` keeps the brand/lot LTR inside an RTL row (`unicode-bidi:plaintext`, the
  built `.rtl` rule).
- **Verbatim, native script, never romanized** — `quantityText` shows `۲۰ واحد`, the table reads
  right-to-left, the lot stays as written. This is contract-level
  ([capture-intelligence-design.md Hard constraints](../ai_engine/capture-intelligence-design.md)).
- **Tabular numerals** for the lot/units columns so Persian and Latin digits align.

---

## 3 · Shareable rendering (patient)

The **same report**, rendered on the public `/share/{token}` page — read-only, no login, curated, with
internals withheld. Reuses the built patient-surface chrome (`pf-head`, `sec`, `ba`, `care`, `pf-foot`
from [aesthetics-patient-surface.html](../../apps/frontend/design-prototypes/aesthetics-patient-surface.html)
+ [patientSurface.css](../../apps/frontend/src/features/patient-surface/patientSurface.css)).

### 3.1 What the patient sees

Driven by the **share payload** (the curated snapshot — `SharePayload`: clinic, patientName, title,
visitDate, **sections** `{label, body}`, **media** `{captureId, caption}`, **aftercare** `{name, body}`):

- A warm clinic header (logo, name, `سلام سارا 👋`, visit title + date).
- **Curated before/after** — the same pairs/slider as clinical (the patient *wants* the slider — it's the
  result), but only the photos the doctor included.
- **Patient-appropriate sections only** — `visit-summary`, `concern-goals`, `plan-followup`, `aftercare`
  by default; the doctor *may* include `assessment` but it's **off by default** (clinician findings can
  be alarming out of context). The **treatment table is never shared as a table** — at most a plain-words
  "what we did" line, and **lots are always withheld** (§4).
- **Aftercare** as a ticked checklist (the `care`/`ps-care` component).
- A `Private link · this is everything shared with you` footer — the trust close.

### 3.2 The curation control (clinic side)

Sharing is an **explicit, curated** clinic action with a **per-share preview** — the built
`Share with patient` sheet ([aesthetics-report.html FRAME 2](../../apps/frontend/design-prototypes/aesthetics-report.html)).
This design renders that sheet against the **synthesized** report (Pro pre-fills it):

- **Toggle rows** per includable element: each before/after pair, each patient-appropriate **section**,
  the **aftercare template** (with `Change`). Defaults: before/after **on**, summary/goals/plan/aftercare
  **on**, assessment **off**, everything internal **absent** (not even a toggle).
- A persistent **"Always withheld"** line (lock icon) listing the internals (§4) — so the doctor *sees*
  the guarantee, building their trust in sharing.
- **Preview** opens the exact patient render; **Send link** is an explicit outward action (confirm before
  sharing — [redesign-aesthetics.md §9](redesign-aesthetics.md)). The link is **revocable**; a
  revoked/expired/unknown link resolves to one indistinguishable "no longer available" state (no
  existence leak — the built `PatientSharePage` behavior, preserved).

*Why the doctor curates, not the AI:* the patient artifact is the clinic's professional output and a
trust/liability surface; the human decides what leaves the building. The AI *pre-fills* a sensible
default; the doctor *approves* it.

---

## 4 · Clinical-vs-shared — what's shown and withheld

The single reconciliation table. The rule: **the patient sees a curated subset of the same report;
internals are withheld at the contract (server) layer, not just hidden in the UI** — the share endpoint
only ever sends the curated snapshot ([PatientSharePage](../../apps/frontend/src/features/patient-surface/PatientSharePage.tsx),
[shareApi](../../apps/frontend/src/features/patient-surface/shareApi.ts)), so internals **cannot** appear
on the patient page.

| Report element | Clinical (in-app) | Shareable (patient) | Why |
| --- | --- | --- | --- |
| Visit summary | shown | shown (default on) | the friendly "what happened today" |
| Concern / goals | shown | shown (default on) | reassures the patient they were heard |
| **Assessment** | shown | **opt-in, default OFF** | clinician findings can alarm out of context |
| **Treatment table** (area·product·brand·units) | full table | **never as a table**; optional plain-words line | structure is clinic-internal; patients don't read dose tables |
| **Lot / batch #** | shown | **ALWAYS withheld** | internal supply data; per [foundation §4](redesign-foundation.md) / AES-403 |
| **Confidence / uncertainty chips** | shown | **never** | AI-internal; the patient sees a finished artifact |
| **carried-forward / needs-confirm chips** | shown | **never** | internal review state |
| **`evidence` / source capture links** | shown | **never** | raw captures are internal |
| **`supersedesCaptureId` / corrections** | shown (audit) | **never** | internal audit trail |
| Before / after media | all, slider+side-by-side | **curated** subset, slider+side-by-side | the result is the patient's; the doctor picks which |
| Captions | the AI caption | the AI caption (on shared photos) | patient-safe descriptive text |
| Plan & follow-up | shown | shown (default on) | the patient needs their next steps |
| Aftercare | shown | shown (default on) | the core patient takeaway |
| Clinic identity | shown | shown | it's their clinic |
| **National ID / DOB / other visits / raw audio / internal notes** | in-app only | **ALWAYS withheld** | PII + clinic internals; never sent ([foundation §4](redesign-foundation.md)) |
| Report status (Complete/Updating/Organizing) | shown | **never** (the patient gets a finished snapshot) | internal pipeline state |

**Invariant:** *every* "always withheld" row is enforced **server-side** (not in the share payload), so
it is structurally impossible for a UI bug to leak it. The curation control only governs the *opt-in*
rows. *Why server-side:* a withholding guarantee you can only break with a code change isn't a guarantee.

---

## 5 · Resolved decisions (product owner, 2026-06-20)

1. **Assessment on the patient page → opt-in, default OFF.** The doctor *may* include the clinical
   assessment on a shared report, but it's off by default (clinician findings can alarm out of context).
   As designed in §4.
2. **Treatment specifics to the patient → per-clinic setting, default GENERIC (no brand).** The share may
   show a plain-words "what we did" line (`Forehead — anti-wrinkle treatment`) but **omits brand/product
   names by default**; a clinic can opt in to including brands. The treatment **table and all lots stay
   always-withheld server-side** regardless. (Add a per-clinic `share_include_brands` setting in the
   Story-C build; default off.)
3. **Carried-forward dose → the report must NOT read a clean "Complete" while unconfirmed.** Stricter than
   chip-only/"warnings-over-blocking", but **for doses specifically** — a dose is the one field where
   silent completion is a safety risk. An unconfirmed carried-forward dose keeps that item in a
   *"confirm dose"* state and the report reads **needs confirmation** (not `Complete`) until the doctor
   confirms; the rest of the report stays non-blocking/usable.
   **Keystone impact:** the merged Job-3 auto-complete derivation must be gated so an unconfirmed
   carried-forward *dose* doesn't resolve to `complete`; the report-state surface (Track 3 / Story C)
   shows "confirm dose" instead. Synthesis is dormant by default (`report_synthesis_enabled` off), so this
   lands before it's enabled — no live impact in the interim.
