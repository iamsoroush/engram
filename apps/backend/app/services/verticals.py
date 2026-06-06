"""Vertical scaffolding (A0).

`Patient` is universal across verticals; what varies is the **report-required work-unit** — a
clinic **Session**, a radiology **Study**, a pathology **Case**. These are one generic
**Encounter** (today implemented as `Session`), typed by `tenant.vertical` and specialized by a
per-type `Session.attributes` JSONB. v1 ships clinics only and keeps the physical name `Session`;
the presentation **label** comes from the vertical via `encounter_label` so it is never hardcoded
in core/apply logic. The literal `Session → Encounter` rename and per-vertical `attributes` fields
land with the second vertical.
"""

DEFAULT_VERTICAL = "clinic"

# vertical → the presentation label for its report-required work-unit (the Encounter).
ENCOUNTER_LABELS: dict[str, str] = {
    "clinic": "Session",
    "radiology": "Study",
    "pathology": "Case",
}


def normalize_vertical(value: str | None) -> str:
    """Return a supported vertical, defaulting unknown/missing values to 'clinic'."""
    return value if isinstance(value, str) and value in ENCOUNTER_LABELS else DEFAULT_VERTICAL


def encounter_label(vertical: str | None) -> str:
    """The presentation label for the report-required work-unit in this vertical (e.g. 'Session')."""
    return ENCOUNTER_LABELS[normalize_vertical(vertical)]
