# Active Session — Capture surface (redesign, in progress)

Target design for the capture surface. Supersedes the `Live draft`/`Structured report`
parts of [screens/capture.md](screens/capture.md) once Epics C/E of the
[intelligence layer](../intelligence-layer.md) ship. Visual reference:
`apps/frontend/design-prototypes/capture-surface.html`.

## Layout

- One **Clinical report** card. The **Captures | Live report** segmented control sits
  **centered in the card header** (desktop) and full-width on mobile. A **tier** badge
  (Basic/Pro) sits by the title; a quiet `refining…` / `updating…` state sits on the right.
  **No Generate button** — the report is always live.
- A patient row above the card: avatar, name, assignment source (`Reassigned by voice`,
  `Matched by AI`, `Manual`), **View patient**, and **Change · Unassign**.
- Sticky footer: slim **Audio / Photo / Note** buttons (icon + single word).

## Captures tab (B1)

- Chronological feed on a timeline rail; each node shows the **capture type icon**
  (mic / photo / note), color-coded.
- Each capture shows: its content (audio player, photo + caption, or note), the
  **AI-generated text** block (transcript / caption / decorated text) with an inline
  **Edit**, and **effect chips**. (Editing generated text is distinct from the deferred
  report-`edit` intent.) **Generated text renders right-to-left** when it's predominantly
  Persian/Arabic script (farsi or mixed-farsi), LTR otherwise.
- **Title-row badges** (quiet, beside the capture title — they're status, not actions):
  - `Patient assigned → N` / `New patient + assigned → N` — shown on the **assignment-source**
    capture; that capture's card is **highlighted** (tinted + ring) so the origin of the current
    assignment is easy to spot. A close (fuzzy) auto-apply appends `· close match · you said …`.
  - `Added to report` (Pro report contribution).
- **Effect chips** (below the capture):
  - `Suggested: reassign to N` — a **partial (fuzzy) match** or an implicit mention on an
    already-assigned visit, **not applied**. On a partial match it opens the **partial-match
    quick-action surface** (below): the matched-vs-spoken identity + **Keep match · Create new
    instead · Choose another**, with a corner **×** to dismiss. It gets its **own centered row**.
  - a superseded assignment renders struck-through with a `kept for review` micro-note
  - `Out of context · not in report` (card dimmed; + **Mark relevant**)
  - calm state chips: `Transcribing…`, `Saved on this device`
- **Undo** reverts in place (drop the capture's timeline event / contribution and
  recompute); the raw capture is never destroyed.

## Partial-match resolution & disambiguation (H4 + H3)

When AI lands on a *partial* (fuzzy) patient match — e.g. ASR wrote *معاضد* but the DB patient
is *معاصد* — staff get a fast, in-place way to confirm it, reject it for a new patient, pick
someone else, or fix details, **without leaving the capture**. Apply semantics are in the
[contract §5](../intelligence-layer.md); this is the surface.

### The decision matrix (design backbone)

**basis** (explicit | implicit) × **match quality** (exact | partial | none) × **visit state**
(unassigned | already-assigned). Exact and none are settled; **H4 specifies the partial cells**.

| match quality | visit state | basis = explicit | basis = implicit |
| --- | --- | --- | --- |
| **exact** (deterministic) | unassigned | assign | assign (first-identity-wins) |
| **exact** | assigned | reassign (override) | **Suggested: reassign** (not applied) |
| **partial** (fuzzy) | unassigned | **Suggested** → quick actions; **auto-applies** only under H3 `balanced`/`lenient` + single high-confidence candidate | **Suggested** (no auto-apply) |
| **partial** | assigned | **Suggested** → quick actions; **auto-applies** only under H3 `balanced`/`lenient` + single high-confidence candidate | **Suggested** (no auto-apply) |
| **none** (usable identity) | unassigned | create + assign, flagged **verify** (editable) | create + assign, flagged **verify** |
| **none** | assigned | create + assign (override), flagged **verify** | quiet (a bare mention; no chip unless a candidate surfaces) |

Invariants at **every** strictness: a **partial match is never silently applied**; the
national-ID **conflict guard** routes to review; **multiple comparable candidates** route to the
resolver (choose-patient), never auto-apply.

### Capture-card quick actions (the new surface)

On a partial / suggested capture the chip expands to show **what was matched vs. what was spoken**
and one-tap actions:

- **Matched *معاصد* · you said *معاضد*** — the matched (existing) name vs. the spoken/transcribed
  name, shown only when they differ.
- **Keep match** — apply the suggestion; assign the visit to the matched patient, attributed to
  this capture (reversible; the chip resolves to `Patient assigned → N`).
- **Create new patient instead** — opens an inline **New patient details** form (name +
  national ID, **prefilled from the spoken identity**, editable) → confirm to create + assign,
  flagged **verify**. This *is* the edit surface for the new patient (the form doubles as
  "edit details"), and it converges with the no-match create flow — one shared create+edit+verify
  surface. For a matched **existing** patient we never silently rename a shared record from a
  fuzzy capture; changing identity goes through *Create new instead* (or the patient detail screen).
- **Choose another** — open the assignment resolver (search / detected-in-session / create).

The surface is a **full-width card on its own dedicated row** (it never shares a row with status
chips). The quick actions render as real buttons: **Keep match** primary (filled), **Create new
instead** / **Choose another** outlined, **Dismiss** ghost. The per-capture **`Added to report`**
status moves up beside the **capture title** (a quiet badge), keeping the conflict-resolver row
uncluttered.

When H3 strictness **auto-applies** a close match (reversible, with notify), the card shows the
applied chip with a quiet **· close match** note + the matched-vs-spoken line + **Undo**, so a
wrong auto-apply is one tap to revert.

### Match strictness (H3 — lives on the Settings page, B4)

A per-tenant **match strictness** setting moves the single-candidate auto-apply line for fuzzy
matches (deterministic matches and the guards above are unaffected):

- **Strict** (default) — auto-apply only deterministic matches (national ID / exact alias /
  contact). Every fuzzy match is a **Suggested** chip. *(Preserves prior behavior.)*
- **Balanced** — also auto-apply a **single** high-confidence fuzzy match with an **explicit**
  reassignment instruction.
- **Lenient** — same, at a lower confidence threshold.

Until the Settings page (B4) ships, the control sits in the Shell user menu next to Languages.

## Live report tab (B2)

A **document**, in both tiers: a clinic header (logo / name / address) and a patient-info
block, rendered from **template/DB, not AI**.

- **Basic:** chronological body — transcripts + **images shown**, with honest timestamps.
  No synthesis, no chips. (AI patient matching still runs — only enrichment/grouping is Pro.)
- **Pro:** a **template-driven, grouped-by-type** report — fixed sections **Audio notes / Written
  notes / Photos**, **no per-line timestamps** — **rebuilt deterministically (no LLM, no async job)
  as each capture lands**; images embed in the Photos section. The report **template** is the fixed
  aesthetic default today and is **user-uploadable later** (key for radiology/pathology); its name +
  a **Change** affordance live in the report **meta strip**, not the patient block. Out-of-context
  captures are excluded; the meta shows `Generated from N captures · M set aside`. Because regen is
  synchronous there is no "updating/refining" job state — the report is current once captures settle.
- **No manual verify gate.** The report is always live; a session shows a calm, auto-derived
  **Complete** badge once captures are processed, a patient is assigned, and the report is current.
  (The separate "flagged **verify**" above is patient-record verification for an AI-created patient,
  which still exists — it is not a report gate.)

## States

See [states.md](states.md). Offline and AI-out are silent and self-healing; the Captures
view stays fully functional. The only hard stop is durable-storage-full (warn ~80%, guard
before long recordings, export escape hatch, request `navigator.storage.persist()`).
