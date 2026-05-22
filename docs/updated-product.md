# Product

## Product summary

AesMem is an AI-native clinical memory system for aesthetics clinics. It helps doctors capture clinical information quickly during visits and progressively organize it into patient-centered session histories.

The product is designed around real clinical behavior:
- capture first
- organize later
- review naturally during downtime
- never block the user with rigid workflows

---

## Target users

- Aesthetics doctors
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
- Patients
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

States are informative, not blocking.

Example states:
- Capturing
- Processing
- Needs review
- Unassigned
- Verified

Sessions remain reviewable and editable in all states.

Verification should reduce uncertainty, not gate usability.

---

## Patients screen

The patients screen is the main long-term memory view.

Main sections:
- Patients
- Unassigned sessions

Patient cards include:
- patient identity
- summarized history
- session cards
- status badges
- quick actions

Needs-review behavior should appear as lightweight status indicators, not separate workflow queues.

---

## AI behavior

AI progressively generates:
- report drafts
- summaries
- extracted findings
- patient matching suggestions

Raw captures remain available as expandable source material to support trust and review.

Internal AI details should remain mostly hidden unless needed for confidence or recovery.
