from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, CaptureStatus, Patient
from app.schemas.api import AssignPatientRequest, CaptureUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_capture_for_tenant
from app.services.sessions import parse_uuid


def get_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def update_capture(
    db: DbSession,
    principal: CurrentPrincipal,
    capture_id: str,
    request: CaptureUpdate,
) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    if request.status is not None:
        try:
            capture.status = CaptureStatus(request.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid capture status") from exc
    if request.metadata is not None:
        capture.capture_metadata = {**(capture.capture_metadata or {}), **request.metadata}
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="capture.update", target_type="capture", target_id=capture.id)
    db.commit()
    db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def assign_capture_patient(
    db: DbSession,
    principal: CurrentPrincipal,
    capture_id: str,
    request: AssignPatientRequest,
) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    previous = capture.patient_id
    next_patient_id = None
    if request.patient_id:
        next_patient_id = parse_uuid(request.patient_id, "patient_id")
        exists = db.execute(
            select(Patient.id).where(Patient.id == next_patient_id, Patient.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
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
        action="capture.assign_patient",
        target_type="capture",
        target_id=capture.id,
        details={
            "previous_patient_id": str(previous) if previous else None,
            "next_patient_id": str(next_patient_id) if next_patient_id else None,
            "reason": request.reason,
            "source": request.source,
        },
    )
    db.commit()
    db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def capture_metadata(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    return {"captureId": str(capture.id), "metadata": capture.capture_metadata}
