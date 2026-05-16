import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, Capture, FakeJob, OrganizationSource, Patient, Session, SessionStatus
from app.schemas.api import AssignPatientRequest, SessionCreate, SessionUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_session_for_tenant, session_payload


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
        status=SessionStatus.needs_review if patient_id else SessionStatus.unassigned,
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
    return session_payload(session)


def list_sessions(
    db: DbSession,
    principal: CurrentPrincipal,
    status_filter: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = select(Session).where(Session.tenant_id == principal.tenant_id)
    if status_filter:
        try:
            statement = statement.where(Session.status == SessionStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    sessions = db.execute(statement.order_by(Session.updated_at.desc()).limit(min(limit, 100))).scalars()
    return [session_payload(session) for session in sessions]


def get_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    return session_payload(session)


def update_session(db: DbSession, principal: CurrentPrincipal, session_id: str, request: SessionUpdate) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    if request.title is not None:
        session.title = request.title
    if request.summary is not None:
        session.summary = request.summary
    if request.generated_summary is not None:
        session.generated_summary = request.generated_summary
    if request.status is not None:
        try:
            session.status = SessionStatus(request.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.update", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session)


def assign_session_patient(
    db: DbSession,
    principal: CurrentPrincipal,
    session_id: str,
    request: AssignPatientRequest,
) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    previous = session.patient_id
    next_patient_id = require_patient(db, principal.tenant_id, request.patient_id)
    session.patient_id = next_patient_id
    if session.status == SessionStatus.unassigned and next_patient_id:
        session.status = SessionStatus.needs_review
    if next_patient_id:
        for capture in db.execute(
            select(Capture).where(
                Capture.tenant_id == principal.tenant_id,
                Capture.session_id == session.id,
                Capture.patient_id.is_(None),
            )
        ).scalars():
            capture.patient_id = next_patient_id
            capture.capture_metadata = {
                **(capture.capture_metadata or {}),
                "patient_assignment_source": request.source,
                "patient_assignment_reason": request.reason,
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
    return {**session_payload(session), "assignmentSource": request.source}


def start_review(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    session.status = SessionStatus.reviewing
    session.review_started_by_user_id = principal.user_id
    session.review_started_at = datetime.now(timezone.utc)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.review_start", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session)


def verify_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    if session.status not in {SessionStatus.reviewing, SessionStatus.organized}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not ready to verify")
    session.status = SessionStatus.verified
    session.verified_by_user_id = principal.user_id
    session.verified_at = datetime.now(timezone.utc)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.verify", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session)


def reopen_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    if session.status != SessionStatus.verified:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only verified sessions can be reopened")
    session.status = SessionStatus.reopened
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.reopen", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session)


def list_session_captures(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    captures = db.execute(
        select(Capture).where(Capture.tenant_id == principal.tenant_id, Capture.session_id == session.id).order_by(Capture.created_at)
    ).scalars()
    return [capture_payload(capture) for capture in captures]


def list_session_artifacts(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    artifacts = db.execute(
        select(Artifact).where(Artifact.tenant_id == principal.tenant_id, Artifact.session_id == session.id).order_by(Artifact.created_at)
    ).scalars()
    return [artifact_payload(artifact) for artifact in artifacts]


def list_session_fake_jobs(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    jobs = db.execute(
        select(FakeJob).where(FakeJob.tenant_id == principal.tenant_id, FakeJob.session_id == session.id).order_by(FakeJob.created_at)
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
