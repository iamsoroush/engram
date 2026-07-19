"""Smart lists + lot/product recall (Pro; AES-501 / AES-502).

Deterministic, zero-AI lenses over the structured data the Pro synthesis *already* extracts — no new
AI job (the eval gate does not apply). The query substrate is the **live** per-visit treatments at
``Session.extracted_metadata["treatments"]`` (the current set the worker writes after synthesis; the
``SessionReportVersion`` snapshots are for undo/versioning, not "current state") plus the
deterministic photo pairing at ``Capture.metadata["photo_pairing"]`` (AES-104).

Surfaces, all Pro-gated on ``live_report_synthesis`` and tenant-scoped:

- **Smart lists (AES-501)** — a small, curated set of named lenses with live counts:
  ``seen-this-week`` · ``due-to-return`` · ``missing-after-photo``.
- **Lot ledger + recall (AES-502)** — the distinct lots/products in the clinic's extracted data, and
  an **exact** lot (or product) lookup returning every affected patient/visit, grounded in the
  verbatim treatment + evidence, for outreach via the patient channel.

The **AES-705 products/lots registry is postponed**; this reads raw extracted values. The single
aggregation point (``_iter_treatments`` + the ledger/recall builders) is the seam where a registry
later enriches (canonical lot, expiry, "unknown lot") without reshaping the responses. See
``docs/ux/screens/patients.md`` (Lists tab).
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Capture, CaptureStatus, CaptureType, Patient, PatientStatus, Session
from app.services.capabilities import LIVE_REPORT_SYNTHESIS, tenant_has_capability
from app.services.treatment_overlay import performed_treatments

# --- Tunable list predicates (documented; the AES-705 seam to per-product precision) ----------------
SEEN_THIS_WEEK_DAYS = 7
# "Due to return" is recency-based by design: the report's Plan & follow-up is prose (no structured
# follow-up date), so we never parse prose or invent a date. A products registry (AES-705) carrying
# per-product typical duration would upgrade this single threshold to per-product "due to wear off".
DUE_TO_RETURN_DAYS = 84  # 12 weeks

SMART_LIST_KEYS = ("seen-this-week", "due-to-return", "missing-after-photo")


def require_smart_lists_capability(db: DbSession, tenant_id: uuid.UUID) -> None:
    """Gate the smart-lists + lot-recall surface on the Pro ``live_report_synthesis`` capability."""
    if not tenant_has_capability(db, tenant_id, LIVE_REPORT_SYNTHESIS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Smart lists and lot recall are a Pro capability.",
        )


# --- Normalization (exact match folds only case + whitespace; never fuzzy) -------------------------
def normalize_lot(value: str) -> str:
    """Exact-match key: upper-cased, whitespace-collapsed, trimmed. Hyphens/dots are KEPT.

    A recall must not over- or under-match: ``D-4471`` is NOT the same lot as ``D4471``. Different
    spellings of the same alphanumeric core surface separately as "similar lots" (never auto-merged).
    """
    return " ".join(value.strip().upper().split())


def _lot_core(value: str) -> str:
    """Separator-insensitive core (alphanumerics only, upper-cased) — the 'similar lot' grouping."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sort_date(session: Session) -> datetime | None:
    # Anchor recency on the visit's clinical date (captured_at), falling back to the immutable
    # created_at — never the mutable updated_at, which any later edit would bump (a recall/"due to
    # return" must reflect when the visit happened, not when its record was last touched).
    return session.captured_at or session.created_at


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- Treatment helpers -----------------------------------------------------------------------------
def _session_treatments(session: Session) -> list[dict[str, Any]]:
    # Read the OVERLAID treatments (report_version ⊕ overlay): a clinician-corrected lot/dose must reach
    # the recall cohort + lot-recall + smart lists, never the raw AI artifact (AES-1101, the safety case).
    return performed_treatments(session)


def _fmt_num(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _treatment_phrase(treatment: dict[str, Any]) -> str | None:
    """A short, verbatim "Dysport 20u, forehead" from one extracted treatment (clinical content)."""
    name = treatment.get("brand") or treatment.get("product")
    if not isinstance(name, str) or not name.strip():
        return None
    quantity = treatment.get("quantityText")
    if not (isinstance(quantity, str) and quantity.strip()) and treatment.get("quantity") is not None:
        unit = treatment.get("unit")
        quantity = f"{_fmt_num(treatment['quantity'])}{(' ' + unit) if isinstance(unit, str) and unit else ''}"
    phrase = f"{name.strip()} {quantity.strip()}" if isinstance(quantity, str) and quantity.strip() else name.strip()
    area = treatment.get("area")
    return f"{phrase}, {area.strip()}" if isinstance(area, str) and area.strip() else phrase


def _treatment_public(treatment: dict[str, Any]) -> dict[str, Any]:
    """The verbatim treatment fields surfaced in a recall row (content; never translated)."""
    return {
        "area": treatment.get("area"),
        "product": treatment.get("product"),
        "brand": treatment.get("brand"),
        "quantity": treatment.get("quantity"),
        "unit": treatment.get("unit"),
        "quantityText": treatment.get("quantityText"),
        "lot": treatment.get("lot"),
        "evidence": treatment.get("evidence"),
        "phrase": _treatment_phrase(treatment),
    }


def _identifying_context(patient: Patient) -> dict[str, Any] | None:
    """The light identifying context a list/cohort row needs (phone matters for outreach)."""
    context = {
        "dateOfBirth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex": patient.sex,
        "phone": patient.phone,
    }
    return context if any(context.values()) else None


# --- Data loading ----------------------------------------------------------------------------------
def _patient_sessions(db: DbSession, tenant_id: uuid.UUID) -> list[tuple[Session, Patient]]:
    """Real, assigned (Session, Patient) pairs for the tenant, newest visit first.

    A "visit" is a session with at least one non-deleted capture — empty draft shells are excluded so
    they never count as a visit in any list (mirrors ``last_visit.py``'s real-visit definition).
    """
    sessions_with_captures = select(Capture.session_id).where(
        Capture.tenant_id == tenant_id,
        Capture.status != CaptureStatus.deleted,
    )
    rows = db.execute(
        select(Session, Patient)
        .join(Patient, Patient.id == Session.patient_id)
        .where(
            Session.tenant_id == tenant_id,
            Patient.tenant_id == tenant_id,
            Patient.status == PatientStatus.active,
            Session.id.in_(sessions_with_captures),
        )
        .order_by(func.coalesce(Session.captured_at, Session.created_at).desc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def _group_by_patient(pairs: list[tuple[Session, Patient]]) -> dict[uuid.UUID, dict[str, Any]]:
    """Group the (already newest-first) pairs by patient → {patient, sessions[]}."""
    grouped: dict[uuid.UUID, dict[str, Any]] = {}
    for session, patient in pairs:
        bucket = grouped.setdefault(patient.id, {"patient": patient, "sessions": []})
        bucket["sessions"].append(session)
    return grouped


def _iter_treatments(pairs: list[tuple[Session, Patient]]) -> Iterator[tuple[Session, Patient, dict[str, Any]]]:
    """Yield the *administered* extracted treatments (the single aggregation point; AES-705 seam).

    Skips ``carriedForward`` items: a carried-forward treatment is a "same as last time" copy of a
    prior visit's dose, so its lot/product was not necessarily used again this visit — counting it
    would over-count the recall cohort and ledger (the original visit already carries the real,
    source-cited row staff verify against). Recall/ledger therefore see real administrations only.
    """
    for session, patient in pairs:
        for treatment in _session_treatments(session):
            if treatment.get("carriedForward") is True:
                continue
            yield session, patient, treatment


# --- Smart-list rows -------------------------------------------------------------------------------
def _patient_row(patient: Patient, *, visit_at: datetime | None, detail: str | None, session_id: str | None = None) -> dict[str, Any]:
    return {
        "patientId": str(patient.id),
        "displayName": patient.display_name,
        "identifyingContext": _identifying_context(patient),
        "sessionId": session_id,
        "visitAt": _iso(visit_at),
        # Content-only (verbatim treatment phrase); the client composes the localized list label.
        "detail": detail,
    }


def _latest_treatment_phrase(session: Session) -> str | None:
    for treatment in _session_treatments(session):
        phrase = _treatment_phrase(treatment)
        if phrase:
            return phrase
    return None


def _seen_this_week_rows(grouped: dict[uuid.UUID, dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(days=SEEN_THIS_WEEK_DAYS)
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for bucket in grouped.values():
        latest = bucket["sessions"][0]
        when = _aware(_sort_date(latest))
        if when is not None and when >= cutoff:
            rows.append((when, _patient_row(bucket["patient"], visit_at=when, detail=_latest_treatment_phrase(latest))))
    rows.sort(key=lambda item: item[0], reverse=True)  # most recent first
    return [row for _, row in rows]


def _due_to_return_rows(grouped: dict[uuid.UUID, dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(days=DUE_TO_RETURN_DAYS)
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for bucket in grouped.values():
        latest = bucket["sessions"][0]
        when = _aware(_sort_date(latest))
        if when is not None and when <= cutoff:
            rows.append((when, _patient_row(bucket["patient"], visit_at=when, detail=_latest_treatment_phrase(latest))))
    rows.sort(key=lambda item: item[0])  # longest overdue (oldest last-visit) first
    return [row for _, row in rows]


def capture_is_unpaired_before(metadata: Any) -> bool:
    """True for a photo paired as ``before`` whose matching ``after`` is missing (AES-104 pairing)."""
    pairing = metadata.get("photo_pairing") if isinstance(metadata, dict) else None
    return isinstance(pairing, dict) and pairing.get("role") == "before" and not pairing.get("pairedCaptureId")


def _missing_after_photo_rows(db: DbSession, tenant_id: uuid.UUID, pairs: list[tuple[Session, Patient]]) -> list[dict[str, Any]]:
    """Visits with a photo paired as ``before`` whose matching ``after`` is missing (AES-104 pairing)."""
    session_ids = [session.id for session, _ in pairs]
    if not session_ids:
        return []
    captures = db.execute(
        select(Capture.session_id, Capture.capture_metadata).where(
            Capture.tenant_id == tenant_id,
            Capture.session_id.in_(session_ids),
            Capture.capture_type == CaptureType.photo,
            Capture.status != CaptureStatus.deleted,
        )
    ).all()
    missing_session_ids: set[uuid.UUID] = set()
    for session_id, metadata in captures:
        if capture_is_unpaired_before(metadata):
            missing_session_ids.add(session_id)
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for session, patient in pairs:  # newest first already
        if session.id not in missing_session_ids:
            continue
        when = _aware(_sort_date(session))
        rows.append(
            (
                when or datetime.min.replace(tzinfo=timezone.utc),
                _patient_row(patient, visit_at=when, detail=_latest_treatment_phrase(session), session_id=str(session.id)),
            )
        )
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows]


def smart_list_counts(db: DbSession, principal: CurrentPrincipal) -> dict[str, Any]:
    """Live counts for the smart-list rail (one round-trip)."""
    require_smart_lists_capability(db, principal.tenant_id)
    pairs = _patient_sessions(db, principal.tenant_id)
    grouped = _group_by_patient(pairs)
    return {
        "counts": {
            "seen-this-week": len(_seen_this_week_rows(grouped)),
            "due-to-return": len(_due_to_return_rows(grouped)),
            "missing-after-photo": len(_missing_after_photo_rows(db, principal.tenant_id, pairs)),
        },
        "dueToReturnWeeks": DUE_TO_RETURN_DAYS // 7,
    }


def smart_list_rows(db: DbSession, principal: CurrentPrincipal, key: str, *, limit: int, offset: int) -> dict[str, Any]:
    """The rows of one smart list (paginated)."""
    require_smart_lists_capability(db, principal.tenant_id)
    if key not in SMART_LIST_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown smart list")
    pairs = _patient_sessions(db, principal.tenant_id)
    if key == "missing-after-photo":
        rows = _missing_after_photo_rows(db, principal.tenant_id, pairs)
    else:
        grouped = _group_by_patient(pairs)
        rows = _seen_this_week_rows(grouped) if key == "seen-this-week" else _due_to_return_rows(grouped)
    total = len(rows)
    return {
        "key": key,
        "rows": rows[offset : offset + limit],
        "limit": limit,
        "offset": offset,
        "total": total,
        "dueToReturnWeeks": DUE_TO_RETURN_DAYS // 7,
    }


# --- Lot ledger + recall ---------------------------------------------------------------------------
def _ledger_from_pairs(pairs: list[tuple[Session, Patient]]) -> dict[str, Any]:
    """Pure ledger aggregation over extracted treatments (no DB / capability — testable)."""
    lots: dict[str, dict[str, Any]] = {}
    products: dict[tuple[str, str], dict[str, Any]] = {}
    for session, patient, treatment in _iter_treatments(pairs):
        lot = treatment.get("lot")
        if isinstance(lot, str) and lot.strip():
            entry = lots.setdefault(
                normalize_lot(lot),
                {"lot": lot.strip(), "product": treatment.get("product"), "brand": treatment.get("brand"), "patients": set(), "sessions": set()},
            )
            entry["patients"].add(patient.id)
            entry["sessions"].add(session.id)
        for name, kind in ((treatment.get("brand"), "brand"), (treatment.get("product"), "product")):
            if isinstance(name, str) and name.strip():
                entry = products.setdefault((kind, name.strip().lower()), {"name": name.strip(), "kind": kind, "patients": set(), "sessions": set()})
                entry["patients"].add(patient.id)
                entry["sessions"].add(session.id)
    lot_list = sorted(
        (
            {"lot": e["lot"], "product": e["product"], "brand": e["brand"], "patientCount": len(e["patients"]), "visitCount": len(e["sessions"])}
            for e in lots.values()
        ),
        key=lambda item: (-item["patientCount"], item["lot"]),
    )
    product_list = sorted(
        (
            {"name": e["name"], "kind": e["kind"], "patientCount": len(e["patients"]), "visitCount": len(e["sessions"])}
            for e in products.values()
        ),
        key=lambda item: (-item["patientCount"], item["name"].lower()),
    )
    return {"lots": lot_list, "products": product_list}


def lot_ledger(db: DbSession, principal: CurrentPrincipal) -> dict[str, Any]:
    """Distinct lots and products in the clinic's extracted data, with patient/visit counts.

    Powers the lookup's suggestions + browse — the clinic picks from what it actually used, never
    typing a lot from memory.
    """
    require_smart_lists_capability(db, principal.tenant_id)
    return _ledger_from_pairs(_patient_sessions(db, principal.tenant_id))


def _cohort_payload(affected: dict[uuid.UUID, dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Shape the grouped {patient → visits → treatments} into sorted cohort rows + a visit count."""
    cohort: list[tuple[datetime, dict[str, Any]]] = []
    visit_count = 0
    for bucket in affected.values():
        visits = sorted(bucket["visits"].values(), key=lambda v: _aware(_sort_date(v["session"])) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        visit_count += len(visits)
        latest = _aware(_sort_date(visits[0]["session"])) if visits else None
        patient = bucket["patient"]
        cohort.append(
            (
                latest or datetime.min.replace(tzinfo=timezone.utc),
                {
                    "patientId": str(patient.id),
                    "displayName": patient.display_name,
                    "identifyingContext": _identifying_context(patient),
                    "visits": [
                        {"sessionId": str(v["session"].id), "visitAt": _iso(_sort_date(v["session"])), "treatments": v["treatments"]}
                        for v in visits
                    ],
                },
            )
        )
    cohort.sort(key=lambda item: item[0], reverse=True)  # most recently affected patient first
    return [row for _, row in cohort], visit_count


def _recall_from_pairs(pairs: list[tuple[Session, Patient]], *, lot: str | None, product: str | None) -> dict[str, Any]:
    """Pure recall matching over extracted treatments (no DB / capability — testable).

    Lot match is exact (case/whitespace-folded only); different spellings of the same alphanumeric
    core surface in ``similar`` — never folded into the affected list. Each affected row carries the
    verbatim treatment + evidence so staff can verify every inclusion before outreach.
    """
    lot_query = lot.strip() if isinstance(lot, str) and lot.strip() else None
    product_query = product.strip() if isinstance(product, str) and product.strip() else None
    if not lot_query and not product_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a lot or product to recall")

    affected: dict[uuid.UUID, dict[str, Any]] = {}
    similar: dict[str, dict[str, Any]] = {}

    if lot_query:
        query_norm = normalize_lot(lot_query)
        query_core = _lot_core(lot_query)
        for session, patient, treatment in _iter_treatments(pairs):
            value = treatment.get("lot")
            if not (isinstance(value, str) and value.strip()):
                continue
            if normalize_lot(value) == query_norm:
                bucket = affected.setdefault(patient.id, {"patient": patient, "visits": {}})
                visit = bucket["visits"].setdefault(session.id, {"session": session, "treatments": []})
                visit["treatments"].append(_treatment_public(treatment))
            # Only group as "similar" on a non-empty shared core, so a separators-only query (e.g. "-")
            # never collides every separators-only lot into the similar list.
            elif query_core and _lot_core(value) == query_core:
                entry = similar.setdefault(normalize_lot(value), {"lot": value.strip(), "patients": set(), "sessions": set()})
                entry["patients"].add(patient.id)
                entry["sessions"].add(session.id)
        kind, value_out, normalized_out = "lot", lot_query, query_norm
    else:
        needle = product_query.lower()
        for session, patient, treatment in _iter_treatments(pairs):
            names = [treatment.get("brand"), treatment.get("product")]
            if any(isinstance(n, str) and n.strip().lower() == needle for n in names):
                bucket = affected.setdefault(patient.id, {"patient": patient, "visits": {}})
                visit = bucket["visits"].setdefault(session.id, {"session": session, "treatments": []})
                visit["treatments"].append(_treatment_public(treatment))
        kind, value_out, normalized_out = "product", product_query, product_query

    cohort, visit_count = _cohort_payload(affected)
    similar_list = sorted(
        ({"lot": e["lot"], "patientCount": len(e["patients"]), "visitCount": len(e["sessions"])} for e in similar.values()),
        key=lambda item: (-item["patientCount"], item["lot"]),
    )
    return {
        "kind": kind,
        "value": value_out,
        "normalized": normalized_out,
        "patientCount": len(cohort),
        "visitCount": visit_count,
        "affected": cohort,
        "similar": similar_list,
    }


def lot_recall(db: DbSession, principal: CurrentPrincipal, *, lot: str | None = None, product: str | None = None) -> dict[str, Any]:
    """Every patient/visit that received a given lot (exact) or product (case-insensitive)."""
    require_smart_lists_capability(db, principal.tenant_id)
    return _recall_from_pairs(_patient_sessions(db, principal.tenant_id), lot=lot, product=product)
