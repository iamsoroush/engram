import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, OrganizationSource, Patient, PatientStatus, Session, SessionStatus


STALE_ASSIGNMENT_KEYS = {
    "patient_assignment_source",
    "patient_assignment_reason",
    "ai_patient_action",
    "ai_patient_assignment_basis",
    "ai_patient_creation_basis",
    "patient_action_badges",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def patient_assignment_event(
    *,
    source: str,
    action: str,
    patient_id: uuid.UUID | None,
    display_name: str | None,
    reason: str | None,
    capture_id: uuid.UUID | None = None,
    created: bool = False,
    action_metadata: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
    assigned_at: str | None = None,
    effective_at: str | None = None,
) -> dict[str, Any]:
    """Build a durable patient assignment timeline event."""
    assigned_at_value = assigned_at or utc_now_iso()
    return {
        "schemaVersion": "2026-06-03.patient-assignment-event.v1",
        "id": str(uuid.uuid4()),
        "source": source,
        "action": action,
        "captureId": str(capture_id) if capture_id else None,
        "patientId": str(patient_id) if patient_id else None,
        "displayName": display_name,
        "created": created,
        "assigned": patient_id is not None,
        "reason": reason,
        "assignedAt": assigned_at_value,
        "effectiveAt": effective_at or assigned_at_value,
        "actorUserId": str(actor_user_id) if actor_user_id else None,
        "actionMetadata": action_metadata,
    }


def append_patient_assignment_event(metadata: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    timeline = metadata.get("patient_assignment_timeline")
    events = [item for item in timeline if isinstance(item, dict)] if isinstance(timeline, list) else []
    if not events:
        legacy_event = legacy_patient_assignment_event(metadata)
        if legacy_event is not None:
            events.append(legacy_event)
    return {**metadata, "patient_assignment_timeline": [*events, event]}


def legacy_patient_assignment_event(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Project older AI patient action metadata into the timeline shape."""
    action = metadata.get("active_patient_assignment_action")
    if not isinstance(action, dict):
        action = metadata.get("ai_patient_action")
    if not isinstance(action, dict) or not action.get("patientId"):
        return None
    patient_information = action.get("patientInformation")
    if isinstance(patient_information, dict):
        has_explicit_identity = any(
            isinstance(patient_information.get(key), str) and patient_information[key].strip()
            for key in ("raw_mentioned_name", "national_id", "phone", "email")
        )
        if not has_explicit_identity:
            return None
    capture_id = action.get("captureId") or action.get("basisCaptureId")
    source = action.get("source") if isinstance(action.get("source"), str) else "ai-engine"
    return {
        "schemaVersion": "2026-06-03.patient-assignment-event.v1",
        "id": str(uuid.uuid4()),
        "source": source,
        "action": action.get("action") if isinstance(action.get("action"), str) else "matched_and_assigned",
        "captureId": str(capture_id) if capture_id else None,
        "patientId": str(action.get("patientId")),
        "displayName": action.get("displayName") if isinstance(action.get("displayName"), str) else None,
        "created": action.get("created") is True,
        "assigned": action.get("assigned") is not False,
        "reason": action.get("reason") if isinstance(action.get("reason"), str) else metadata.get("patient_assignment_reason"),
        "assignedAt": action.get("assignedAt") if isinstance(action.get("assignedAt"), str) else utc_now_iso(),
        "effectiveAt": legacy_patient_action_time(action),
        "actorUserId": action.get("actorUserId") if isinstance(action.get("actorUserId"), str) else None,
        "actionMetadata": action,
    }


def assignment_source_for_event(event: dict[str, Any]) -> str | None:
    source = event.get("source")
    if source == "staff":
        return "staff"
    if source in {"ai-engine", "ai_engine"}:
        return "ai_created" if event.get("created") else "ai_matched"
    return source if isinstance(source, str) else None


def legacy_patient_action_time(action: dict[str, Any]) -> str:
    for key in ("effectiveAt", "assignedAt"):
        value = action.get(key)
        if isinstance(value, str):
            return value
    return utc_now_iso()


def _capture_is_out_of_context(capture: Capture) -> bool:
    """Whether a capture is flagged out-of-context and not staff-overridden (local copy to avoid a
    cycle with session_processing; mirrors ``capture_is_out_of_context``)."""
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    marker = metadata.get("out_of_context")
    if not isinstance(marker, dict) or marker.get("overridden_by_staff") is True:
        return False
    return marker.get("present") is True


def active_patient_assignment_event(db: DbSession, session: Session) -> dict[str, Any] | None:
    """Return the latest timeline event whose source capture still exists and is in context.

    A deleted capture, or an out-of-context one (AI-flagged or staff-marked), is not a valid
    assignment basis (A-F4): an OOC capture must never file or keep a visit filed under a patient, and
    marking a capture out-of-context after the fact de-effects the assignment it drove — like deletion.
    """
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    timeline = metadata.get("patient_assignment_timeline")
    if not isinstance(timeline, list):
        return None
    valid_events = []
    for index, event in enumerate([item for item in timeline if isinstance(item, dict)]):
        capture_id = event.get("captureId")
        if not capture_id:
            valid_events.append((event_sort_time(event), index, event))
            continue
        parsed_capture_id = parse_uuid_or_none(capture_id)
        if parsed_capture_id is None:
            continue
        capture = db.execute(
            select(Capture).where(
                Capture.id == parsed_capture_id,
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalar_one_or_none()
        if capture is not None and not _capture_is_out_of_context(capture):
            valid_events.append((event_sort_time(event), index, event))
    if not valid_events:
        return None
    return max(valid_events, key=lambda item: (item[0], item[1]))[2]


def parse_uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def event_sort_time(event: dict[str, Any]) -> datetime:
    value = event.get("effectiveAt") or event.get("assignedAt")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def archive_orphaned_ai_patient(db: DbSession, *, patient_id: uuid.UUID | None, actor_user_id: uuid.UUID | None) -> bool:
    """Soft-delete an AI-created unverified patient a reassignment just orphaned (incident Fix 6).

    The chokepoint form of ``captures._archive_orphaned_ai_patient``: when the active assignment moves
    away from an AI-created *unverified* patient that nothing else references (no assigned session, no
    live capture), archive it (reversible ``status=archived``) so a mis-transcribed spoken identity
    doesn't leave a ghost patient behind — for BOTH staff and AI-driven reassignment. Never touches a
    verified/human-created patient or one with remaining dependents. Best-effort; returns whether it archived.
    """
    if patient_id is None:
        return False
    from app.auth.service import audit
    from app.services.feedback import record_feedback_event
    from app.services.patients import is_ai_created_unverified_patient

    patient = db.get(Patient, patient_id)
    if patient is None or not is_ai_created_unverified_patient(patient):
        return False
    has_session = db.execute(
        select(Session.id).where(Session.tenant_id == patient.tenant_id, Session.patient_id == patient.id).limit(1)
    ).scalar_one_or_none()
    has_capture = db.execute(
        select(Capture.id).where(
            Capture.tenant_id == patient.tenant_id,
            Capture.patient_id == patient.id,
            Capture.status != CaptureStatus.deleted,
        ).limit(1)
    ).scalar_one_or_none()
    if has_session is not None or has_capture is not None:
        return False
    patient.status = PatientStatus.archived
    audit(
        db,
        tenant_id=patient.tenant_id,
        actor_user_id=actor_user_id,
        action="patient.archive_orphaned_ai",
        target_type="patient",
        target_id=patient.id,
    )
    record_feedback_event(
        db,
        tenant_id=patient.tenant_id,
        actor_user_id=actor_user_id,
        kind="correction",
        ai_output_type="patient_match",
        patient_id=patient.id,
        context={"action": "reassign_orphaned_ai_patient"},
    )
    return True


def apply_active_patient_assignment(db: DbSession, session: Session) -> None:
    """Apply the latest valid assignment event to the session and capture badges.

    When the active patient changes, an AI-created unverified patient the session just moved away from
    is archived if nothing else references it (incident Fix 6) — for staff and AI reassignment alike.
    """
    former_patient_id = session.patient_id
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    event = active_patient_assignment_event(db, session)
    next_patient_id = None
    if event and event.get("patientId"):
        try:
            next_patient_id = uuid.UUID(str(event["patientId"]))
        except ValueError:
            next_patient_id = None
    patient = None
    if next_patient_id is not None:
        patient = db.execute(
            select(Patient).where(Patient.id == next_patient_id, Patient.tenant_id == session.tenant_id)
        ).scalar_one_or_none()
        if patient is None:
            next_patient_id = None

    source = assignment_source_for_event(event) if event else None
    action_metadata = event.get("actionMetadata") if isinstance(event, dict) and isinstance(event.get("actionMetadata"), dict) else None
    next_metadata = {
        key: value
        for key, value in metadata.items()
        if key not in {"patient_assignment_source", "patient_assignment_reason", "ai_patient_action", "active_patient_assignment_action"}
    }
    if event and next_patient_id is not None:
        next_metadata = {
            **next_metadata,
            "patient_assignment_source": source,
            "patient_assignment_reason": event.get("reason"),
            "active_patient_assignment_action": event,
            **({"ai_patient_action": action_metadata or event} if source in {"ai_created", "ai_matched"} else {}),
        }
    session.patient_id = next_patient_id
    session.extracted_metadata = next_metadata
    if next_patient_id is not None:
        session.organization_source = OrganizationSource.ai_engine if source in {"ai_created", "ai_matched"} else OrganizationSource.staff
        if session.status in {SessionStatus.unassigned, SessionStatus.draft, SessionStatus.processing}:
            session.status = SessionStatus.needs_review

    active_capture_id = event.get("captureId") if event and event.get("captureId") else None
    for capture in db.execute(
        select(Capture).where(
            Capture.tenant_id == session.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
    ).scalars():
        capture.patient_id = next_patient_id
        capture.capture_metadata = {
            key: value
            for key, value in (capture.capture_metadata or {}).items()
            if key not in STALE_ASSIGNMENT_KEYS
        }
        if active_capture_id and str(capture.id) == str(active_capture_id) and source in {"ai_created", "ai_matched"}:
            badges = ["assignment"]
            if event.get("created"):
                badges.append("creation")
            capture.capture_metadata = {
                **capture.capture_metadata,
                "patient_assignment_source": source,
                "patient_assignment_reason": event.get("reason"),
                "ai_patient_action": action_metadata or event,
                "ai_patient_assignment_basis": True,
                "patient_action_badges": badges,
                **({"ai_patient_creation_basis": True} if event.get("created") else {}),
            }

    # Incident Fix 6: if this recompute moved the visit off an AI-created unverified patient, archive
    # that patient when nothing else references it. Flush first so the just-repointed captures/session
    # are visible to the dependents check (this session uses autoflush=False).
    if former_patient_id is not None and str(former_patient_id) != str(next_patient_id):
        db.flush()
        actor = parse_uuid_or_none(event.get("actorUserId")) if isinstance(event, dict) else None
        archive_orphaned_ai_patient(db, patient_id=former_patient_id, actor_user_id=actor)
