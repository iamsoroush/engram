# Clinical Memory Workflow

## User Goal

Keep capturing with almost no friction while Memara quietly saves, organizes, summarizes, and asks for help only when human judgment is required.

## Entry Points

- App navigation opens `Clinical Memory`.
- The route remains `/#patients` for compatibility.
- The default tab is `Today`.
- Patient search or a patient row opens patient detail and timeline.
- A Needs input item opens the smallest decision surface needed to resolve it.

## Main Flow

1. User opens Clinical Memory.
2. `Today` shows session-first visit work for the current day. Session cards can include patient context, but they must identify the visit and use explicit labels such as `Session:` and `Updated:`. Selecting a session card opens that visit in Active Session; visible buttons are reserved for focused tasks.
3. User searches or opens `Patients` to find patient-memory-first rows.
4. Patient rows show natural memory summaries, latest visit references, exact needs-input labels when relevant, and one primary action. They do not show nested session lists, nor an "active session" badge (live work lives in `Today`).
5. User opens a patient to view the patient assistant summary and timeline.
6. Timeline sessions are grouped by actual session time: `Today`, `Earlier this week`, and `Older`.
7. Each session is summarized in human language and has one primary action.
8. `Needs input` contains only the critical decisions the user must make — **assign patient** (unassigned), **choose patient** (ambiguous/uncertain match or national-ID conflict), and **verify patient** (an AI-created patient awaiting confirmation) — plus a critical storage warning. Routine summary confirmation is not a needs-input item. The list is backend-computed and matches the per-patient card badges exactly. Each item explains the decision, visit, known patient or backend-proposed candidates, reason, and smallest resolver action. Selecting a needs-input card opens the visit in Active Session; the primary button opens the focused resolver (verify opens the visit, where the AI-created-patient panel lives).
9. The persistent capture bar stays visible so the user always understands where captures will go and whether they are safely saved.

## Resolver Rules

- `Assign patient` opens assignment, not the active session page.
- `Choose patient` opens patient choice, not the active session page.
- Backend patient-match candidates are suggestions only; staff confirmation is required before any assignment or memory update.
- `Review summary` opens the summary review flow.
- `Review storage` opens storage guidance or review.
- Session card selection opens the visit when the user needs broader context.

## Partial-match resolution (on the capture card)

A *partial* (fuzzy) patient match is resolved **in place on the capture**, not only in the
resolver. Apply semantics: [intelligence-layer §5](../../intelligence-layer.md); the surface and
the basis × match-quality × visit-state decision matrix:
[redesign-capture-surface.md](../redesign-capture-surface.md) "Partial-match resolution".

- A partial match is **never silently applied** (CLAUDE.md: never mis-assign). It shows the
  **matched-vs-spoken identity** ("Matched *معاصد* · you said *معاضد*") and one-tap actions:
  - **Keep match** — assign the visit to the matched patient (attributed to this capture; reversible).
  - **Create new patient instead** — opens an inline **New patient details** form (name +
    national ID, prefilled from the *spoken* identity, editable) → create + assign, flagged
    **verify**. The form is also the "edit details" surface and converges with the no-match create
    flow. A matched **existing** record is never silently renamed from a fuzzy capture.
  - **Choose another** — open the assignment resolver (search / detected-in-session / create).
- A close match **auto-applies** (reversible, with a `· close match` note + Undo) only under the
  per-tenant **match strictness** setting (`balanced`/`lenient`) with a single high-confidence
  candidate and an explicit reassignment instruction. The national-ID **conflict guard** and
  ambiguous-multi-candidate routing win at every strictness level.

## Involved Screens

- [Clinical Memory](../screens/patients.md)
- [Session review](../screens/session-review.md)
- [Search](../screens/search.md)

## Related Shared Rules

- Assistant-state, Needs input, and offline behavior: [UX states](../states.md)
- Clinical Memory layout and patient-card summary fallback: [Clinical Memory screen](../screens/patients.md)
