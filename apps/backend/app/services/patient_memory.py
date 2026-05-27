import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import (
    Capture,
    CaptureStatus,
    Patient,
    PatientIdentifier,
    PatientStatus,
    Session,
    SessionStatus,
)
from app.services.patients import get_patient, normalize_identifier, patient_payload
from app.services.sessions import parse_uuid

ACTIVE_SESSION_STATUSES = {
    SessionStatus.draft,
    SessionStatus.processing,
    SessionStatus.needs_review,
    SessionStatus.reviewing,
    SessionStatus.reopened,
}
NEEDS_INPUT_STATUSES = {
    SessionStatus.needs_review,
    SessionStatus.reopened,
}
EMPTY_SUMMARY = "No memory summary yet."


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_sort_date(session: Session) -> datetime | None:
    return session.captured_at or session.updated_at or session.created_at


def _capture_count(metadata: dict[str, Any]) -> int:
    value = metadata.get("capture_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _generated_summary(session: Session | None) -> str | None:
    if session is None:
        return None
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    summaries = metadata.get("summaries") if isinstance(metadata.get("summaries"), dict) else {}
    for value in (
        session.generated_summary,
        summaries.get("patient_memory"),
        summaries.get("clinical"),
        summaries.get("short"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _rule_based_summary(session: Session | None, session_count: int, capture_count: int) -> str | None:
    if session is None:
        return None
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    latest_type = metadata.get("latest_capture_type")
    type_label = {
        "audio": "audio",
        "photo": "photos",
        "note": "notes",
    }.get(latest_type if isinstance(latest_type, str) else "", "captures")
    if session.summary and session.summary.strip():
        return session.summary.strip()
    if capture_count:
        visit_word = "visit" if session_count == 1 else f"{session_count} visits"
        capture_word = "capture" if capture_count == 1 else "captures"
        return f"Latest {visit_word} has {capture_count} {capture_word}; recent {type_label} are saved."
    if session_count:
        return f"{session_count} visit{'s' if session_count != 1 else ''} saved."
    return None


def _metadata_sentence(session: Session | None, capture_count: int) -> str | None:
    if session is None:
        return None
    date_value = _session_sort_date(session)
    date_text = date_value.date().isoformat() if date_value else "recently"
    capture_text = f"{capture_count} capture{'s' if capture_count != 1 else ''}"
    return f"Last updated {date_text}. {capture_text} in the latest visit."


def _summary_parts(session: Session | None, session_count: int, capture_count: int) -> dict[str, str | None]:
    generated = _generated_summary(session)
    rule_based = _rule_based_summary(session, session_count, capture_count)
    metadata_sentence = _metadata_sentence(session, capture_count)
    if generated:
        return {
            "summary": generated,
            "summary_source": "generated",
            "generated_summary": generated,
            "rule_based_summary": rule_based,
            "metadata_sentence": metadata_sentence,
        }
    if rule_based:
        return {
            "summary": rule_based,
            "summary_source": "rule-based",
            "generated_summary": None,
            "rule_based_summary": rule_based,
            "metadata_sentence": metadata_sentence,
        }
    if metadata_sentence:
        return {
            "summary": metadata_sentence,
            "summary_source": "metadata",
            "generated_summary": None,
            "rule_based_summary": None,
            "metadata_sentence": metadata_sentence,
        }
    return {
        "summary": EMPTY_SUMMARY,
        "summary_source": "empty",
        "generated_summary": None,
        "rule_based_summary": None,
        "metadata_sentence": None,
    }


def _identifying_context(patient: Patient) -> dict[str, Any] | None:
    payload = patient_payload(patient)
    context = {
        "dateOfBirth": payload.get("dateOfBirth"),
        "sex": payload.get("sex"),
        "phone": payload.get("phone"),
        "nationalId": payload.get("nationalId"),
    }
    return context if any(context.values()) else None


def _row_payload(
    *,
    patient: Patient,
    latest_session: Session | None,
    active_session: Session | None,
    session_count: int,
    active_session_count: int,
    latest_capture_count: int,
    all_verified: bool,
    needs_input: bool,
) -> dict[str, Any]:
    latest_visit_at = _session_sort_date(latest_session) if latest_session else None
    updated_at = max(
        value
        for value in (patient.updated_at, latest_session.updated_at if latest_session else None, latest_visit_at)
        if value is not None
    )
    summary = _summary_parts(latest_session, session_count, latest_capture_count)
    latest_metadata = None
    if latest_session is not None:
        latest_metadata = {
            "sessionId": str(latest_session.id),
            "title": latest_session.title,
            "status": latest_session.status.value,
            "summary": latest_session.summary,
            "captureCount": latest_capture_count,
            "capturedAt": _iso(latest_session.captured_at),
            "updatedAt": _iso(latest_session.updated_at),
        }
    return {
        "patientId": str(patient.id),
        "displayName": patient.display_name,
        "identifyingContext": _identifying_context(patient),
        "summary": summary["summary"],
        "summarySource": summary["summary_source"],
        "generatedSummary": summary["generated_summary"],
        "ruleBasedSummary": summary["rule_based_summary"],
        "metadataSentence": summary["metadata_sentence"],
        "latestSessionMetadata": latest_metadata,
        "latestSessionId": str(latest_session.id) if latest_session else None,
        "activeSessionId": str(active_session.id) if active_session else None,
        "activeSessionCount": active_session_count,
        "sessionCount": session_count,
        "verified": all_verified,
        "needsInput": needs_input,
        "latestVisitAt": _iso(latest_visit_at),
        "updatedAt": _iso(updated_at),
    }


def _capture_counts(db: DbSession, tenant_id: uuid.UUID, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(Capture.session_id, func.count(Capture.id))
        .where(
            Capture.tenant_id == tenant_id,
            Capture.session_id.in_(session_ids),
            Capture.status != CaptureStatus.deleted,
        )
        .group_by(Capture.session_id)
    ).all()
    return {session_id: count for session_id, count in rows}


def _coerce_clinician_id(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clinicianId") from exc


def _patient_base_statement(principal: CurrentPrincipal, query: str | None, clinician_id: uuid.UUID | None):
    latest_session_at = func.max(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at)).label(
        "latest_session_at"
    )
    session_count = func.count(Session.id).label("session_count")
    statement = (
        select(Patient, latest_session_at, session_count)
        .outerjoin(
            Session,
            (Session.patient_id == Patient.id)
            & (Session.tenant_id == principal.tenant_id),
        )
        .where(Patient.tenant_id == principal.tenant_id, Patient.status == PatientStatus.active)
    )
    if clinician_id is not None:
        statement = statement.where(Session.created_by_user_id == clinician_id)
    if query:
        pattern = f"%{query.strip()}%"
        normalized_identifier = normalize_identifier(query)
        identifier_patient_ids = select(PatientIdentifier.patient_id).where(
            PatientIdentifier.tenant_id == principal.tenant_id,
            PatientIdentifier.normalized_value.ilike(f"%{normalized_identifier}%"),
        )
        statement = statement.where(
            or_(
                Patient.display_name.ilike(pattern),
                Patient.legal_first_name.ilike(pattern),
                Patient.legal_last_name.ilike(pattern),
                Patient.phone.ilike(pattern),
                Patient.email.ilike(pattern),
                Patient.id.in_(identifier_patient_ids),
            )
        )
    return statement.group_by(Patient.id)


def list_patient_memory(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    query: str | None,
    memory_filter: str,
    clinician_id: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Return flat, paginated patient-memory rows for Clinical Memory."""
    if memory_filter not in {"recent", "active", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filter")
    clinician_uuid = _coerce_clinician_id(clinician_id)
    base = _patient_base_statement(principal, query, clinician_uuid)
    if memory_filter == "recent":
        base = base.having(func.count(Session.id) > 0)
    if memory_filter == "active":
        active_count = func.count(Session.id).filter(Session.status.in_(ACTIVE_SESSION_STATUSES))
        base = base.having(active_count > 0)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(func.coalesce(func.max(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at)), Patient.updated_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    patients = [row[0] for row in rows]
    patient_ids = [patient.id for patient in patients]
    session_statement = select(Session).where(
        Session.tenant_id == principal.tenant_id,
        Session.patient_id.in_(patient_ids),
    )
    if clinician_uuid is not None:
        session_statement = session_statement.where(Session.created_by_user_id == clinician_uuid)
    sessions = (
        db.execute(
            session_statement.order_by(
                Session.patient_id,
                func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc(),
            )
        ).scalars().all()
        if patient_ids
        else []
    )
    sessions_by_patient: dict[uuid.UUID, list[Session]] = {}
    for session in sessions:
        sessions_by_patient.setdefault(session.patient_id, []).append(session)
    capture_counts = _capture_counts(db, principal.tenant_id, [session.id for session in sessions])

    items = []
    for patient in patients:
        patient_sessions = sessions_by_patient.get(patient.id, [])
        latest_session = patient_sessions[0] if patient_sessions else None
        active_sessions = [session for session in patient_sessions if session.status in ACTIVE_SESSION_STATUSES]
        active_session = active_sessions[0] if active_sessions else None
        session_count = len(patient_sessions)
        items.append(
            _row_payload(
                patient=patient,
                latest_session=latest_session,
                active_session=active_session,
                session_count=session_count,
                active_session_count=len(active_sessions),
                latest_capture_count=(
                    capture_counts.get(latest_session.id, _capture_count(latest_session.extracted_metadata))
                    if latest_session
                    else 0
                ),
                all_verified=bool(patient_sessions)
                and all(session.status == SessionStatus.verified for session in patient_sessions),
                needs_input=any(session.status in NEEDS_INPUT_STATUSES for session in patient_sessions),
            )
        )
    return {"items": items, "limit": limit, "offset": offset, "total": total}


def _timeline_group_label(value: datetime | None) -> str:
    if value is None:
        return "Earlier"
    today = datetime.now(timezone.utc).date()
    visit_date = value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    delta_days = (today - visit_date).days
    if delta_days == 0:
        return "Today"
    if 0 < delta_days <= 7:
        return "Earlier this week"
    return "Earlier"


def get_patient_memory_detail(db: DbSession, principal: CurrentPrincipal, patient_id: str) -> dict[str, Any]:
    """Return one patient memory summary with timeline sessions."""
    patient = get_patient(db, principal.tenant_id, patient_id)
    sessions = db.execute(
        select(Session)
        .where(Session.tenant_id == principal.tenant_id, Session.patient_id == parse_uuid(patient_id, "patient_id"))
        .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc())
    ).scalars().all()
    capture_counts = _capture_counts(db, principal.tenant_id, [session.id for session in sessions])
    latest_session = sessions[0] if sessions else None
    active_sessions = [session for session in sessions if session.status in ACTIVE_SESSION_STATUSES]
    patient_row = _row_payload(
        patient=patient,
        latest_session=latest_session,
        active_session=active_sessions[0] if active_sessions else None,
        session_count=len(sessions),
        active_session_count=len(active_sessions),
        latest_capture_count=(
            capture_counts.get(latest_session.id, _capture_count(latest_session.extracted_metadata))
            if latest_session
            else 0
        ),
        all_verified=bool(sessions) and all(session.status == SessionStatus.verified for session in sessions),
        needs_input=any(session.status in NEEDS_INPUT_STATUSES for session in sessions),
    )
    timeline_sessions = []
    for session in sessions:
        sort_date = _session_sort_date(session)
        capture_count = capture_counts.get(session.id, _capture_count(session.extracted_metadata or {}))
        summary = _summary_parts(session, 1, capture_count)
        timeline_sessions.append(
            {
                "sessionId": str(session.id),
                "title": session.title,
                "status": session.status.value,
                "summary": summary["summary"],
                "generatedSummary": summary["generated_summary"],
                "ruleBasedSummary": summary["rule_based_summary"],
                "captureCount": capture_count,
                "verified": session.status == SessionStatus.verified,
                "needsInput": session.status in NEEDS_INPUT_STATUSES,
                "groupLabel": _timeline_group_label(sort_date),
                "sortDate": _iso(sort_date),
                "capturedAt": _iso(session.captured_at),
                "updatedAt": _iso(session.updated_at),
            }
        )
    group_map: dict[str, list[dict[str, Any]]] = {}
    for item in timeline_sessions:
        group_map.setdefault(item["groupLabel"], []).append(item)
    groups = [
        {"label": label, "sessions": group_map[label]}
        for label in ("Today", "Earlier this week", "Earlier")
        if label in group_map
    ]
    return {
        "patient": patient_row,
        "sessions": timeline_sessions,
        "groups": groups,
    }
