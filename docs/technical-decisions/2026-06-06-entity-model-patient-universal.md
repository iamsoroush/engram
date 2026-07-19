# Entity Model: Patient Universal, Encounter Generalizes By Vertical (A0) (2026-06-06)

`Patient` is first-class and **universal** across verticals and stays the assignment target — it
is **not** abstracted. The entity that generalizes is the report-required **Encounter**
(`Session` for clinics; `Study`/`Case` for radiology/pathology), one per `Report`. v1 implements
the Encounter as today's `Session` and does **not** rename it.

Implemented scaffolding (A0): `tenant.vertical` (default `aesthetics`; the legacy `clinic` value
is normalized to `aesthetics`) plus a reserved
`session.attributes` JSONB extension point for per-vertical fields (kept separate from
`extracted_metadata`). The work-unit presentation label is derived from the vertical via
`services/verticals.encounter_label` (aesthetics/therapy→"Session", radiology→"Study", pathology→"Case") and
surfaced on the `TenantProfile` (`vertical`, `encounterLabel`) — it must not be hardcoded in
core/apply logic. The literal `Session → Encounter` rename and the per-type `attributes` fields
land with the second vertical.

See [architecture.md](../architecture.md) "Entity Model (verticals)" and
[intelligence-layer.md §2](../intelligence-layer.md).
