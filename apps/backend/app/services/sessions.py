import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, Capture, CaptureStatus, AiJob, OrganizationSource, Patient, Session, SessionStatus
from app.schemas.api import AssignPatientRequest, SessionCreate, SessionSaveRequest, SessionUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_session_for_tenant, session_payload
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    patient_assignment_event,
)
from app.services.reporting import DEFAULT_REPORT_TEMPLATE_KEY, structured_report_from_markdown_body


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_uuid(value: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {name}") from exc


def require_patient(db: DbSession, tenant_id: uuid.UUID, patient_id: str | None) -> uuid.UUID | None:
    if patient_id is None:
        return None
    parsed = parse_uuid(patient_id, "patient_id")
    exists = db.execute(select(Patient.id).where(Patient.id == parsed, Patient.tenant_id == tenant_id)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return parsed


def create_session(db: DbSession, principal: CurrentPrincipal, request: SessionCreate) -> dict[str, Any]:
    patient_id = require_patient(db, principal.tenant_id, request.patient_id)
    session = Session(
        tenant_id=principal.tenant_id,
        patient_id=patient_id,
        status=SessionStatus.draft,
        title=request.title,
        summary=request.summary,
        organization_source=OrganizationSource.none,
        created_by_user_id=principal.user_id,
        captured_at=parse_datetime(request.captured_at),
    )
    db.add(session)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.create",
        target_type="session",
        target_id=session.id,
        details={"patient_id": str(patient_id) if patient_id else None},
    )
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def save_session(db: DbSession, principal: CurrentPrincipal, session_id: str, request: SessionSaveRequest) -> dict[str, Any]:
    """Request session-level report processing without enforcing workflow state."""
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    capture_exists = db.execute(
        select(Capture.id)
        .where(
            Capture.tenant_id == principal.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
        .limit(1)
    ).scalar_one_or_none()
    if capture_exists is None:
        session.report_template_key = request.report_template_key or session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="session.process.request_empty",
            target_type="session",
            target_id=session.id,
            details={"report_template_key": session.report_template_key},
        )
        db.commit()
        db.refresh(session)
        return {"session": session_payload(session, db), "processingJob": None}

    from app.services.ai_jobs import regenerate_session_report_if_idle

    session.report_template_key = request.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY
    # The live report regenerates automatically and deterministically as captures land (no AI job,
    # no LLM), so the manual Generate button is gone; this endpoint now just rebuilds on demand
    # (e.g. an explicit retry). No-op while the capture chain is still processing.
    regenerate_session_report_if_idle(
        db,
        tenant_id=principal.tenant_id,
        session_id=session.id,
        created_by_user_id=principal.user_id,
        force=True,
    )
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.save",
        target_type="session",
        target_id=session.id,
        details={"report_template_key": session.report_template_key},
    )
    db.commit()
    db.refresh(session)
    return {"session": session_payload(session, db), "processingJob": None}


def list_sessions(
    db: DbSession,
    principal: CurrentPrincipal,
    status_filter: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    from app.services.caseload import is_federated_caseload

    statement = select(Session).where(Session.tenant_id == principal.tenant_id)
    # Therapy: the active session is user-scoped (foundation §7) — a clinician lists only their own
    # sessions. Aesthetics is a shared workspace, so no owner scoping there.
    if is_federated_caseload(db, principal.tenant_id):
        statement = statement.where(Session.created_by_user_id == principal.user_id)
    if status_filter:
        try:
            statement = statement.where(Session.status == SessionStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    sessions = db.execute(statement.order_by(Session.updated_at.desc()).limit(min(limit, 100))).scalars()
    return [session_payload(session, db) for session in sessions]


def get_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    return session_payload(session, db)


def update_session(db: DbSession, principal: CurrentPrincipal, session_id: str, request: SessionUpdate) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    if request.title is not None:
        session.title = request.title
    if request.summary is not None:
        session.summary = request.summary
    if request.generated_summary is not None:
        session.generated_summary = request.generated_summary
    if request.generated_report is not None:
        session.generated_report = request.generated_report
        session.report_model = structured_report_from_markdown_body(
            title=session.title,
            body=request.generated_report,
            template_key=session.report_template_key,
        )
    if request.report_model is not None:
        session.report_model = request.report_model
    if request.report is not None:
        body = request.report.get("body")
        if isinstance(body, str):
            session.generated_report = body
            session.report_model = structured_report_from_markdown_body(
                title=session.title,
                body=body,
                template_key=session.report_template_key,
                findings=request.findings,
            )
        metadata = {**metadata, "progressive_report": request.report}
    if request.summaries is not None:
        short = request.summaries.get("short")
        if isinstance(short, str):
            session.summary = short
            session.generated_summary = short
        metadata = {**metadata, "summaries": request.summaries}
    if request.findings is not None:
        metadata = {**metadata, "findings": request.findings}
    if request.processing_status is not None:
        metadata = {**metadata, "processing_status": request.processing_status}
    if request.extracted_metadata is not None:
        metadata = {**metadata, **request.extracted_metadata}
    if metadata != (session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}):
        session.extracted_metadata = metadata
    if request.status is not None:
        try:
            session.status = SessionStatus(request.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.update", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def assign_session_patient(
    db: DbSession,
    principal: CurrentPrincipal,
    session_id: str,
    request: AssignPatientRequest,
) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    previous = session.patient_id
    next_patient_id = require_patient(db, principal.tenant_id, request.patient_id)
    patient = (
        db.execute(
            select(Patient).where(Patient.id == next_patient_id, Patient.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if next_patient_id
        else None
    )
    existing_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    # When staff apply a per-capture suggestion, attribute the assignment to that capture so it
    # becomes the source (and the prior basis capture turns into a switchable alternate).
    basis_capture = None
    if request.basis_capture_id and next_patient_id:
        basis_capture = db.execute(
            select(Capture).where(
                Capture.id == parse_uuid(request.basis_capture_id, "basis_capture_id"),
                Capture.tenant_id == principal.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalar_one_or_none()
    event = patient_assignment_event(
        source=request.source or "staff",
        action="manually_assigned" if next_patient_id else "manually_unassigned",
        patient_id=next_patient_id,
        display_name=patient.display_name if patient else None,
        reason=request.reason,
        capture_id=basis_capture.id if basis_capture is not None else None,
        actor_user_id=principal.user_id,
    )
    session.extracted_metadata = append_patient_assignment_event(existing_metadata, event)
    apply_active_patient_assignment(db, session)
    if basis_capture is not None:
        # The suggestion on the now-applied capture is consumed — drop it so the chip clears.
        basis_capture.capture_metadata = {
            key: value
            for key, value in (basis_capture.capture_metadata or {}).items()
            if key != "patient_match_candidate"
        }
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.assign_patient",
        target_type="session",
        target_id=session.id,
        details={
            "previous_patient_id": str(previous) if previous else None,
            "next_patient_id": str(next_patient_id) if next_patient_id else None,
            "reason": request.reason,
            "source": request.source,
        },
    )
    db.commit()
    db.refresh(session)
    return {**session_payload(session, db), "assignmentSource": request.source}


def start_review(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    session.status = SessionStatus.reviewing
    session.review_started_by_user_id = principal.user_id
    session.review_started_at = datetime.now(timezone.utc)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.review_start", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def list_session_captures(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    captures = db.execute(
        select(Capture)
        .where(
            Capture.tenant_id == principal.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
        .order_by(Capture.created_at)
    ).scalars()
    payloads = [capture_payload(capture) for capture in captures]
    if db.dirty:
        db.commit()
    return payloads


def list_session_artifacts(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    artifacts = db.execute(
        select(Artifact).where(Artifact.tenant_id == principal.tenant_id, Artifact.session_id == session.id).order_by(Artifact.created_at)
    ).scalars()
    return [artifact_payload(artifact) for artifact in artifacts]


def list_session_ai_jobs(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    jobs = db.execute(
        select(AiJob).where(AiJob.tenant_id == principal.tenant_id, AiJob.session_id == session.id).order_by(AiJob.created_at)
    ).scalars()
    return [
        {
            "id": str(job.id),
            "sessionId": str(job.session_id) if job.session_id else None,
            "captureId": str(job.capture_id) if job.capture_id else None,
            "jobType": job.job_type.value,
            "status": job.status.value,
            "generatedBy": job.generated_by,
            "resultMetadata": job.result_metadata,
            "errorMessage": job.error_message,
            "createdAt": job.created_at.isoformat() if job.created_at else None,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job in jobs
    ]
