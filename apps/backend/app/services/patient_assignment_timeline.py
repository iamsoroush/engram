import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, OrganizationSource, Patient, Session, SessionStatus
from app.services.patient_safety import drop_session_safety_flags, sync_patient_safety_flags
from app.services.synthesis_escalation import SYNTHESIS_ESCALATE_KEY


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


def active_patient_assignment_event(db: DbSession, session: Session) -> dict[str, Any] | None:
    """Return the latest timeline event whose source still exists."""
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
        capture_exists = db.execute(
            select(Capture.id).where(
                Capture.id == parsed_capture_id,
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalar_one_or_none()
        if capture_exists is not None:
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


# A true reassignment (patient A→B, or B→∅) invalidates session state that was computed against the
# WRONG patient. These user/AI-state keys are cleared so a forced re-synthesis recomputes them for the
# correct patient (S-F2 carry-forward confirmations, S-F6 cross-visit safety reconcile). The visit's own
# treatment_overlay (human field edits on THIS visit's rows) is patient-independent and is NOT cleared.
_REASSIGNMENT_INVALIDATED_KEYS = ("confirmed_carried_forward", "safety_reconciliation")


def _invalidate_reassigned_session_state(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop wrong-patient-derived synthesis state on a true reassignment; force a fresh escalated run.

    The stored treatments/report stay in place (so the report never blanks) but are marked stale +
    not-current, and the next synthesis is escalated — a reassignment is proof the prior context was
    wrong. The forced re-synthesis (dispatched by the caller) recomputes carry-forward + safety-reconcile
    against the correct patient; the patient-scoped version cache (report_versions) prevents a stale
    cross-patient cache-hit from short-circuiting it.
    """
    next_metadata = {key: value for key, value in metadata.items() if key not in _REASSIGNMENT_INVALIDATED_KEYS}
    next_metadata["generated_output_stale"] = True
    next_metadata[SYNTHESIS_ESCALATE_KEY] = True
    record = next_metadata.get("report_synthesis")
    if isinstance(record, dict) and record.get("status") == "current":
        next_metadata["report_synthesis"] = {**record, "status": "stale"}
    return next_metadata


def apply_active_patient_assignment(db: DbSession, session: Session) -> None:
    """Apply the latest valid assignment event to the session and capture badges.

    This is the single choke point where ``session.patient_id`` changes (staff assign endpoint, AI-driven
    assignment, capture-delete de-effect all route through it), so it also keeps the cross-visit safety
    store consistent (S-F1) and invalidates wrong-patient-derived synthesis state on a true reassignment
    (S-F2/S-F6). The caller commits and — where AI jobs are reachable — force-dispatches the re-synthesis.
    """
    previous_patient_id = session.patient_id
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
    # A true reassignment: an existing patient changed to a different one (or was cleared). Initial filing
    # of an unassigned visit (previous is None) is NOT a reassignment.
    is_true_reassignment = previous_patient_id is not None and str(previous_patient_id) != (
        str(next_patient_id) if next_patient_id is not None else ""
    )
    if is_true_reassignment:
        next_metadata = _invalidate_reassigned_session_state(next_metadata)
    session.patient_id = next_patient_id
    session.extracted_metadata = next_metadata
    # (S-F1) Keep the cross-visit safety store consistent with the assignment: drop this visit's
    # contribution from a patient it left, and (re-)project its kept flags onto the patient it now points
    # at. Done here — the one place patient_id changes — so the AI-driven reassign path (which never went
    # through the staff endpoint's explicit drop/sync) is covered too.
    if is_true_reassignment and previous_patient_id is not None:
        old_patient = db.get(Patient, previous_patient_id)
        if old_patient is not None:
            drop_session_safety_flags(old_patient, session.id)
    if next_patient_id is not None:
        new_patient = db.get(Patient, next_patient_id)
        if new_patient is not None:
            sync_patient_safety_flags(new_patient, session)
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
