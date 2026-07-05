"""User-authored treatment overlay (AES-1101) — the treatments analogue of the safety overlay.

A Pro treatment row is the AI artifact; a clinician correction to one of its fields is a **human-owned
overlay entry** applied on top (``report_version ⊕ overlay``), never part of the artifact and never
overwritten by a re-synthesis — the same load-bearing invariant the safety/aftercare overlays use
([pipeline-versioning D2](../../../docs/architecture/pipeline-versioning.md)). This module is the single
source of truth for that overlay's mechanics; it is a **leaf** (imports only models + stdlib), so
``session_processing`` / ``session_contracts`` / the read-site projections all depend on it, never the
reverse.

It owns:

* the deterministic, content-anchored **treatment_key** (``compute_treatment_key`` / ``stamp_treatment_keys``)
  — Unicode-general normalization, anchored on ``areaCode|norm(product)`` when the synthesis emitted a
  canonical ``areaCode`` (language-independent), ``norm(area)`` as the legacy fallback, an ordinal suffix
  on collision;
* the render/projection **fold** (``effective_treatments``) — the ONLY treatments read for recall,
  lot-recall cohorts, smart lists, and the patient-memory brief, so a corrected lot/dose is used everywhere;
* the post-synthesis **re-bind pass** (``rebind_treatment_overlay``) that re-anchors each overlay entry to
  the freshly-synthesized rows (exact key → bound; shared source-capture + normalized area, ``priorKey``
  tie-break → re-bind; else the entry drops with its source-de-effected row), refreshing ``aiValue`` so a
  fresh-extraction disagreement surfaces (``{aiValue, value}``) instead of silently overwriting;
* the carried-forward **auto-confirm collapse** (``overlay_satisfied_carry_forward_keys``) — a dose edit
  IS the confirmation, so the row stops asking "confirm dose" (epic Q4);
* the pure overlay-entry mutations the endpoints call (``upsert_overlay_edit`` / ``remove_overlay_edit``).

Field VALUES stay clinical content in the report language (never translated); only the mechanics live here.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.models import Session

# v1 is field-edit-only (epic Q2); row add/remove are v2. These are the editable treatment fields.
TREATMENT_OVERLAY_FIELDS: tuple[str, ...] = ("area", "product", "brand", "quantity", "lot")
# How an edited FIELD maps onto a treatment ROW key. A dose ("quantity") overrides the verbatim
# display anchor (quantityText, which takes precedence over quantity+unit in every renderer).
_OVERLAY_FIELD_TO_ROW: dict[str, str] = {
    "area": "area",
    "product": "product",
    "brand": "brand",
    "lot": "lot",
    "quantity": "quantityText",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Unicode-general normalization + the content-anchored treatment key -----------------------------
def _fold_digits(text: str) -> str:
    """Fold every Unicode decimal digit (Persian/Arabic/Latin/…) to its 0-9 value; leave prose intact."""
    return "".join(str(d) if (d := unicodedata.decimal(ch, None)) is not None else ch for ch in text)


def norm_token(value: Any) -> str:
    """Unicode-GENERAL key normalization (NFKC · casefold · digit-fold · whitespace-collapse).

    Not Persian-specific: fa/ar, Turkish (dotted/dotless i via casefold, ç/ş intact), and Latin all
    normalize identically with no per-language tables, so a Turkish clinic gets the same key stability
    as a Persian one. Deterministic + reproducible — the whole point of an anchored (not LLM-emitted) key.
    """
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    text = text.casefold()
    text = _fold_digits(text)
    return " ".join(text.split())


def _first_source_capture_id(treatment: dict[str, Any]) -> str:
    sources = treatment.get("sourceCaptureIds")
    if isinstance(sources, list):
        for value in sources:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _treatment_area_anchor(treatment: dict[str, Any]) -> str:
    """The area anchor: the canonical ``areaCode`` when synthesis emitted one (language-independent),
    else ``norm(area)`` for legacy rows. Products/brands are mostly Latin already, so anchoring the key
    on ``areaCode|norm(product)`` makes it survive a report-language switch / a non-fa-en clinic."""
    area_code = treatment.get("areaCode")
    if isinstance(area_code, str) and area_code.strip():
        return norm_token(area_code)
    return norm_token(treatment.get("area"))


def _treatment_key_core(treatment: dict[str, Any]) -> str:
    """``t|<areaCode|norm(area)>|norm(product)|<first sourceCaptureId>`` — before collision ordinal."""
    return f"t|{_treatment_area_anchor(treatment)}|{norm_token(treatment.get('product'))}|{_first_source_capture_id(treatment)}"


def compute_treatment_key(treatment: dict[str, Any], *, used: dict[str, int] | None = None) -> str:
    """Deterministic content-anchored key for one treatment row (ordinal suffix on collision).

    ``used`` tracks core-key occurrences WITHIN one synthesis output so two same-area+product rows from
    one capture (the accepted collision limitation) disambiguate as ``…#1``, ``…#2`` in array order.
    """
    core = _treatment_key_core(treatment)
    if used is None:
        return core
    ordinal = used.get(core, 0)
    used[core] = ordinal + 1
    return core if ordinal == 0 else f"{core}#{ordinal}"


def stamp_treatment_keys(treatments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return the treatments with a stable ``treatmentKey`` stamped on each (ordinal-disambiguated)."""
    used: dict[str, int] = {}
    stamped: list[dict[str, Any]] = []
    for treatment in treatments or []:
        if not isinstance(treatment, dict):
            continue
        row = dict(treatment)
        row["treatmentKey"] = compute_treatment_key(row, used=used)
        stamped.append(row)
    return stamped


def carried_forward_key(treatment: dict[str, Any]) -> str:
    """Stable id (``<areaCode|norm(area)>|norm(product)``) for a carried-forward dose to confirm (Q3).

    Anchored on the same language-independent area anchor + normalized product as ``treatmentKey`` (S-F7),
    so a confirmed carried dose stays confirmed across a re-synthesis that rewords the display strings or
    a report-language switch («گونه» → «گونه‌ها», fa → en) — instead of minting a new key that re-opens
    "confirm dose" and flips a closed visit back to incomplete. NOTE: distinct from ``treatmentKey``
    (which also folds in the source capture). The confirm-dose overlay (``confirmed_carried_forward``) and
    the review row are both keyed on this.
    """
    return f"{_treatment_area_anchor(treatment)}|{norm_token(treatment.get('product'))}"


# --- Reading stored treatments + the overlay --------------------------------------------------------
def _metadata(session: Session) -> dict[str, Any]:
    return session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}


def _treatments_of(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("treatments")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _overlay_of(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("treatment_overlay")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def stored_treatments(session: Session) -> list[dict[str, Any]]:
    """The raw AI-artifact treatments (``extracted_metadata['treatments']``) — before the overlay fold."""
    return _treatments_of(_metadata(session))


def session_treatment_overlay(session: Session) -> list[dict[str, Any]]:
    """The user-authored ``treatment_overlay`` entries (validated to dicts)."""
    return _overlay_of(_metadata(session))


def _row_field_value(treatment: dict[str, Any], field: str) -> str | None:
    """The current AI value of an editable field, as the human-comparable display string.

    ``quantity`` renders the verbatim dose (``quantityText`` if present, else ``quantity + unit``) — the
    same anchor the overlay's human value replaces.
    """
    if field == "quantity":
        quantity_text = treatment.get("quantityText")
        if isinstance(quantity_text, str) and quantity_text.strip():
            return quantity_text.strip()
        quantity = treatment.get("quantity")
        if isinstance(quantity, (int, float)) and not isinstance(quantity, bool):
            unit = treatment.get("unit")
            number = str(int(quantity)) if isinstance(quantity, float) and quantity.is_integer() else str(quantity)
            return f"{number}{(' ' + unit) if isinstance(unit, str) and unit.strip() else ''}".strip()
        return None
    value = treatment.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


# --- The render/projection fold (the ONLY treatments any consumer reads) ----------------------------
def effective_treatments(session: Session) -> list[dict[str, Any]]:
    """``report_version ⊕ overlay`` — the stored treatments with human field edits applied.

    THE single treatments read for recall, lot-recall cohorts, smart lists, and the patient-memory
    brief (safety-critical: a corrected lot must reach the recall cohort). A dose edit overrides the
    verbatim ``quantityText`` and clears the now-stale numeric ``quantity``/``unit`` so they can't
    contradict it. Edited fields are tagged in ``overlayEditedFields`` for provenance-aware consumers.
    """
    return effective_treatments_from_metadata(_metadata(session))


def effective_treatments_from_metadata(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    """``effective_treatments`` over a raw ``extracted_metadata`` dict (for SQL-projection read sites)."""
    metadata = metadata if isinstance(metadata, dict) else {}
    edits_by_key: dict[str, dict[str, str]] = {}
    for entry in _overlay_of(metadata):
        if entry.get("op", "edit") != "edit":
            continue  # v1 folds field-edits only; row add/remove are v2
        key = entry.get("treatmentKey")
        field = entry.get("field")
        value = entry.get("value")
        if not isinstance(key, str) or field not in TREATMENT_OVERLAY_FIELDS or not isinstance(value, str):
            continue
        edits_by_key.setdefault(key, {})[field] = value

    folded: list[dict[str, Any]] = []
    for treatment in _treatments_of(metadata):
        edits = edits_by_key.get(treatment.get("treatmentKey"))
        if not edits:
            folded.append(treatment)
            continue
        row = dict(treatment)
        for field, value in edits.items():
            row[_OVERLAY_FIELD_TO_ROW[field]] = value
            if field == "quantity":
                # The human dose leads; drop the AI numeric so the verbatim override is unambiguous.
                row["quantity"] = None
                row["unit"] = None
        row["overlayEditedFields"] = sorted(edits)
        folded.append(row)
    return folded


# --- The post-synthesis re-bind pass ----------------------------------------------------------------
def rebind_treatment_overlay(
    fresh_treatments: list[dict[str, Any]] | None, overlay: list[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-anchor each overlay entry to the freshly-synthesized rows; PARK (never delete) the orphans.

    A human overlay edit (e.g. a corrected lot number) is authoritative user state — a re-synthesis must
    never silently destroy it (S-F4). Per overlay entry, in order:

    1. EXACT ``treatmentKey`` match → bind.
    2. **priorKey-first**: a fresh row that explicitly claims to continue this exact prior key
       (``row.priorKey == entry.treatmentKey``) → bind, *independent of the area filter*. This rescues an
       edit when a re-synthesis re-slugs the area ("cheeks" → "left-cheek"): the priorKey hint — built
       precisely for this — is honored before the area anchor, which would otherwise reject it.
    3. area+source candidate: a fresh row sharing a source capture AND the normalized area.
    4. else the row is gone from this synthesis → the entry is PARKED as an orphan (surfaced as a review
       chip) rather than deleted, so a corrected lot can't silently revert to the wrong AI lot.

    Returns ``(rebound, orphans)``. Every surviving entry's ``aiValue`` is refreshed so a disagreement
    with the human ``value`` surfaces via ``{aiValue, value}`` — never a silent overwrite. Parked orphans
    are re-attempted on the next re-synthesis (pass them back in ``overlay``), so a row that reappears
    re-binds out of the orphan list.
    """
    fresh = [row for row in (fresh_treatments or []) if isinstance(row, dict) and isinstance(row.get("treatmentKey"), str)]
    by_key = {row["treatmentKey"]: row for row in fresh}
    rebound: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    for entry in overlay or []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        if field not in TREATMENT_OVERLAY_FIELDS:
            continue
        entry_key = entry.get("treatmentKey")
        row = by_key.get(entry_key)
        if row is None:
            row = _priorkey_match(entry_key, fresh)
        if row is None:
            row = _rebind_candidate(entry, fresh)
        if row is None:
            orphans.append(_park_orphan_entry(entry))  # source row gone → park, never delete
            continue
        rebound.append(_bind_entry_to_row(entry, row))
    return rebound, orphans


def _priorkey_match(entry_key: Any, fresh: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A fresh row that explicitly continues this exact prior key (``priorKey == entry_key``).

    A first-class re-bind rule, checked BEFORE the area filter — a row echoing the prior key must rescue
    the binding even when a re-synthesis re-keyed its area (S-F4).
    """
    if not isinstance(entry_key, str) or not entry_key:
        return None
    for row in fresh:
        if row.get("priorKey") == entry_key:
            return row
    return None


def _rebind_candidate(entry: dict[str, Any], fresh: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A fresh row sharing a source capture + normalized area with the entry (priorKey breaks ties)."""
    match_area = entry.get("matchArea")
    entry_sources = {value for value in (entry.get("sourceCaptureIds") or []) if isinstance(value, str)}
    entry_key = entry.get("treatmentKey")
    candidates = [
        row
        for row in fresh
        if _treatment_area_anchor(row) == match_area
        and entry_sources & {value for value in (row.get("sourceCaptureIds") or []) if isinstance(value, str)}
    ]
    if not candidates:
        return None
    for row in candidates:  # priorKey tie-break: a row that claims to continue this exact prior key wins
        if row.get("priorKey") == entry_key:
            return row
    return candidates[0]


def _park_orphan_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return the overlay entry marked parked (its value/aiValue/field preserved for the review chip)."""
    parked = dict(entry)
    parked["parked"] = True
    parked.setdefault("parkedAt", _now_iso())
    return parked


def _bind_entry_to_row(entry: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Return the entry re-anchored to ``row``: fresh key + anchor snapshot + refreshed aiValue."""
    bound = dict(entry)
    # A re-bound entry is active again — clear any parked marker from a prior synthesis where it orphaned.
    bound.pop("parked", None)
    bound.pop("parkedAt", None)
    bound["treatmentKey"] = row["treatmentKey"]
    bound["matchArea"] = _treatment_area_anchor(row)
    bound["sourceCaptureIds"] = [value for value in (row.get("sourceCaptureIds") or []) if isinstance(value, str)]
    bound["aiValue"] = _row_field_value(row, entry["field"])  # disagreement (aiValue != value) surfaces in the UI
    return bound


# --- Carried-forward auto-confirm collapse (epic Q4) ------------------------------------------------
def overlay_satisfied_carry_forward_keys(session: Session) -> set[str]:
    """``carried_forward`` keys whose dose a human edited via the overlay — the edit IS the confirmation.

    So a carried-forward row that the clinician re-dosed via the overlay stops asking "confirm dose"
    (``session_is_complete`` unions these with the explicit ``confirmed_carried_forward`` set).
    """
    dose_edited_keys = {
        entry.get("treatmentKey")
        for entry in session_treatment_overlay(session)
        if entry.get("op", "edit") == "edit" and entry.get("field") == "quantity" and isinstance(entry.get("treatmentKey"), str)
    }
    satisfied: set[str] = set()
    for treatment in stored_treatments(session):
        if treatment.get("carriedForward") is True and treatment.get("treatmentKey") in dose_edited_keys:
            satisfied.add(carried_forward_key(treatment))
    return satisfied


# --- Pure overlay-entry mutations the endpoints call ------------------------------------------------
def find_treatment_by_key(treatments: list[dict[str, Any]], treatment_key: str) -> dict[str, Any] | None:
    """The stored treatment row a key binds to (for aiValue snapshot + field-value validation)."""
    for treatment in treatments:
        if treatment.get("treatmentKey") == treatment_key:
            return treatment
    return None


def upsert_overlay_edit(
    overlay: list[dict[str, Any]],
    *,
    treatment: dict[str, Any],
    field: str,
    value: str,
    edited_by_user_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Insert/replace a field edit (last-write-wins per (treatmentKey, field)); return (overlay, aiValue).

    The AI value at edit time is snapshotted so the row can offer Revert-to-AI and, after a later
    re-synthesis, Keep-yours / Use-AI on a disagreement. Area anchor + source captures are snapshotted
    for the re-bind fallback. Pure: mutates + returns the list; the caller persists + commits.
    """
    treatment_key = treatment["treatmentKey"]
    ai_value = _row_field_value(treatment, field)
    kept = [
        entry
        for entry in overlay
        if not (isinstance(entry, dict) and entry.get("treatmentKey") == treatment_key and entry.get("field") == field)
    ]
    kept.append(
        {
            "treatmentKey": treatment_key,
            "field": field,
            "value": value,
            "aiValue": ai_value,
            "matchArea": _treatment_area_anchor(treatment),
            "sourceCaptureIds": [v for v in (treatment.get("sourceCaptureIds") or []) if isinstance(v, str)],
            "editedByUserId": edited_by_user_id,
            "editedAt": _now_iso(),
            "op": "edit",
        }
    )
    return kept, ai_value


def remove_overlay_edit(overlay: list[dict[str, Any]], *, treatment_key: str, field: str) -> list[dict[str, Any]]:
    """Drop the edit for (treatmentKey, field) — Revert-to-AI restores the AI value. Pure."""
    return [
        entry
        for entry in overlay
        if not (isinstance(entry, dict) and entry.get("treatmentKey") == treatment_key and entry.get("field") == field)
    ]
