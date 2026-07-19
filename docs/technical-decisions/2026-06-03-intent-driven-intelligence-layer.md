# Intelligence Layer Is Intent-Driven With An Explicit AI↔Backend↔Frontend Contract (2026-06-03)

Capture intelligence (assignment/reassignment, append, out-of-context) is being redesigned
from "AI extracts identity, backend decides silently" to an explicit, versioned contract:
the AI emits typed intents, the backend applies them with non-destructive, reversible,
capture-attributed semantics, and the frontend renders each capture's effect as a chip.
The `edit` intent and field-level provenance are deferred. Assignment reuses the existing
event-sourced `patient_assignment_timeline` (latest-valid-event-wins, undo by capture
deletion). Tiering (`basic`/`pro`) gates how much intelligence runs. `Patient` stays the universal
assignment target; the entity that generalizes across verticals is the *encounter*
(`Session` today; Study/Case in radiology/pathology), typed by `tenant.vertical`.

See [intelligence-layer.md](../intelligence-layer.md) for the full v1 contract and open decisions.
