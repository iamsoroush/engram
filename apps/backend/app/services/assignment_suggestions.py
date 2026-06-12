"""Deterministic assign-later suggestion (aesthetics-Basic, AES-301).

Capture-first never blocks: a visit can be captured before a patient is chosen, and filing catches
up. In Basic (zero AI) the "Assign to …?" suggestion is **rule-based**, not a match — it points at
the patient most likely meant by the open clinic context: someone currently in a chair (an *active*
visit), else the most recently seen patient. The resolver still offers Assign / Keep unassigned /
Create new; nothing is assigned silently.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Patient, PatientStatus, Session, SessionStatus
from app.services.capture_storage import get_session_for_tenant
from app.services.sessions import parse_uuid

SUGGESTION_SCHEMA_VERSION = "2026-06-12.assign-later-suggestion.v1"
# A visit that is genuinely live right now (being captured / processed / reopened) — its patient is
# "in the chair". The resting review states are not active.
ACTIVE_SESSION_STATUSES = {SessionStatus.draft, SessionStatus.processing, SessionStatus.reopened}
# How many recent assigned visits to scan when building the candidate list.
RECENT_SESSION_SCAN = 60
MAX_SUGGESTION_CANDIDATES = 5


def _sort_date(session: Session) -> datetime:
    return session.captured_at or session.updated_at or session.created_at or datetime.min


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def suggest_session_assignment(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    """Return a deterministic "Assign to …?" suggestion for an unassigned visit (AES-301).

    Args:
        db: Active database session.
        principal: Authenticated staff principal (tenant scope).
        session_id: The visit awaiting assignment.

    Returns:
        ``{"schemaVersion", "sessionId", "alreadyAssigned", "suggestion", "candidates"}``.
        ``suggestion`` is the top candidate or ``None``; each candidate carries ``patientId``,
        ``displayName``, ``basis`` (``active_patient`` | ``recent_patient``), ``reason``, and
        ``lastVisitAt``. ``alreadyAssigned`` short-circuits to no suggestion.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    if session.patient_id is not None:
        return {
            "schemaVersion": SUGGESTION_SCHEMA_VERSION,
            "sessionId": str(session.id),
            "alreadyAssigned": True,
            "suggestion": None,
            "candidates": [],
        }

    recent_sessions = db.execute(
        select(Session)
        .where(
            Session.tenant_id == principal.tenant_id,
            Session.patient_id.is_not(None),
            Session.id != session.id,
        )
        .order_by(Session.updated_at.desc())
        .limit(RECENT_SESSION_SCAN)
    ).scalars().all()

    # Latest assigned visit per patient, and whether that patient is currently active.
    latest_by_patient: dict[uuid.UUID, Session] = {}
    active_patient_ids: set[uuid.UUID] = set()
    for candidate_session in recent_sessions:
        patient_id = candidate_session.patient_id
        if patient_id is None:
            continue
        current = latest_by_patient.get(patient_id)
        if current is None or _sort_date(candidate_session) > _sort_date(current):
            latest_by_patient[patient_id] = candidate_session
        if candidate_session.status in ACTIVE_SESSION_STATUSES:
            active_patient_ids.add(patient_id)

    if not latest_by_patient:
        return {
            "schemaVersion": SUGGESTION_SCHEMA_VERSION,
            "sessionId": str(session.id),
            "alreadyAssigned": False,
            "suggestion": None,
            "candidates": [],
        }

    patients = {
        patient.id: patient
        for patient in db.execute(
            select(Patient).where(
                Patient.tenant_id == principal.tenant_id,
                Patient.status == PatientStatus.active,
                Patient.id.in_(list(latest_by_patient.keys())),
            )
        ).scalars()
    }

    candidates: list[dict[str, Any]] = []
    for patient_id, latest_session in latest_by_patient.items():
        patient = patients.get(patient_id)
        if patient is None:
            continue
        is_active = patient_id in active_patient_ids
        candidates.append(
            {
                "patientId": str(patient_id),
                "displayName": patient.display_name,
                "basis": "active_patient" if is_active else "recent_patient",
                "reason": (
                    "This patient has a visit open right now."
                    if is_active
                    else "This is the most recently seen patient."
                ),
                "lastVisitAt": _iso(_sort_date(latest_session)),
                "_active": is_active,
                "_sort": _sort_date(latest_session),
            }
        )
    # Active patients first, each group most-recent-first — the open patient outranks mere recency.
    candidates.sort(key=lambda item: (item["_active"], item["_sort"]), reverse=True)
    for candidate in candidates:
        candidate.pop("_active", None)
        candidate.pop("_sort", None)
    capped = candidates[:MAX_SUGGESTION_CANDIDATES]
    return {
        "schemaVersion": SUGGESTION_SCHEMA_VERSION,
        "sessionId": str(session.id),
        "alreadyAssigned": False,
        "suggestion": capped[0] if capped else None,
        "candidates": capped,
    }
