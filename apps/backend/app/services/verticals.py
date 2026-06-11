"""Vertical scaffolding (A0).

`Patient` is universal across verticals; what varies is the **report-required work-unit** — a
capture-first **Session**/**Visit**, a radiology **Study**, a pathology **Case**. These are one
generic **Encounter** (today implemented as `Session`), typed by `tenant.vertical` and specialized
by a per-type `Session.attributes` JSONB. The presentation **label** comes from the vertical via
`encounter_label` so it is never hardcoded in core/apply logic. The literal `Session → Encounter`
rename and per-vertical `attributes` fields land with the second vertical.

Spine-A verticals (aesthetics, therapy, dermatology) share the capture-first core; radiology and
pathology are report-first/multi-actor (Spines B/C). `aesthetics` is the default — it is the current
product. The legacy `clinic` value maps onto `aesthetics` so old data/strings stay valid.
"""

DEFAULT_VERTICAL = "aesthetics"

# vertical → the presentation label for its report-required work-unit (the Encounter).
ENCOUNTER_LABELS: dict[str, str] = {
    "aesthetics": "Session",
    "therapy": "Session",
    "dermatology": "Visit",
    "radiology": "Study",
    "pathology": "Case",
}

# Legacy/aliased vertical values mapped onto a canonical vertical (kept valid for old data/strings).
_LEGACY_ALIASES: dict[str, str] = {
    "clinic": "aesthetics",
}


def normalize_vertical(value: str | None) -> str:
    """Return a supported vertical, mapping legacy values and defaulting unknown/missing to 'aesthetics'."""
    if isinstance(value, str):
        if value in ENCOUNTER_LABELS:
            return value
        if value in _LEGACY_ALIASES:
            return _LEGACY_ALIASES[value]
    return DEFAULT_VERTICAL


def encounter_label(vertical: str | None) -> str:
    """The presentation label for the report-required work-unit in this vertical (e.g. 'Session')."""
    return ENCOUNTER_LABELS[normalize_vertical(vertical)]
