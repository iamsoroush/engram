# Product

## Product summary

Engram is an AI-native clinical memory system for aesthetics and therapy clinics (dermatology next). It helps doctors capture clinical information quickly during visits and progressively organize it into patient-centered session histories.

The product is designed around real clinical behavior:

- capture first
- organize later
- review naturally during downtime
- never block the user with rigid workflows

---

## Target users

- Aesthetics and therapy clinicians
- Small and medium clinics
- Clinical assistants involved in documentation

---

## Core problem

Doctors often document visits using scattered tools such as:

- phone photos
- Apple Notes
- voice recordings
- messaging apps

This creates friction during the visit and weak longitudinal memory across sessions.

---

## Product promise

Fast capture with progressively organized clinical memory.

---

## Core concepts

### Patient

The long-term memory container.

A patient includes:

- AI-generated summarized history
- session timeline
- quick actions
- unresolved session indicators

### Session

The primary working object.

A session continuously evolves:

- captures are added
- AI processing updates the report
- metadata is extracted
- summaries improve progressively

Sessions remain accessible in all states.

### Capture

Supported capture types:

- audio
- photo
- text

Capture must always feel immediate and lightweight.

---

## Navigation model

Top-left navigation:

- Active Session
- Clinical Memory
- Search

Persistent bottom actions:

- Record audio
- Take photo
- Write note

---

## Active session workspace

The capture screen is also the active session workspace.

The user captures and reviews in the same surface.

The workspace includes:

- session header
- clinical report
- collapsible summary
- collapsible extracted findings
- expandable captures
- contextual quick actions

The report area always exists, even while processing is incomplete.

---

## Session states

States are assistant-like, informative, and not blocking.

Sessions remain reviewable and editable in all states.

Verification should reduce uncertainty, not gate usability.

---

## Clinical Memory

Clinical Memory replaces the old Patients screen as the main long-term memory surface.

It should feel like a calm intelligent assistant, not a database browser. The default view optimizes for current work and recent memory instead of showing every patient and every session.

Main sections:

- Today: session-first current-day visit work.
- Patients: patient-memory-first cards without nested session cards.
- Needs input: decision-first inbox for human choices and data-safety actions.

Patient cards include:

- patient identity
- an assistant-style natural memory sentence
- latest visit reference, active-session badge, and exact needs-input label when relevant
- one clear primary action

Long-term session history belongs in patient detail and timeline views, not nested on the main list.

Needs-input actions open focused resolvers such as patient assignment, patient choice, summary review, or storage review. They should not use the active session page as the primary action.

See [UX Overview](ux/overview.md) for screen-level behavior and state language.

---

## AI behavior

AI progressively generates:

- report drafts
- summaries
- extracted findings
- patient matching suggestions

Raw captures remain available as expandable source material to support trust and review.

Internal AI details should remain hidden in normal use. When AI is unavailable, the app keeps capture working and quietly organizes later.
