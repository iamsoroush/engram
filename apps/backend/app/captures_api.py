"""Capture routes: source-file upload, capture CRUD, media streaming, reprocessing.

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/captures``, ``app/services/capture_storage``, and ``app/services/ai_jobs``; the
byte-range and metadata-form plumbing lives in ``app/http``.
"""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.http.forms import parse_metadata_form
from app.http.responses import ranged_file_response
from app.schemas.captures import CaptureUpdate
from app.schemas.patients import AssignPatientRequest
from app.services.ai_jobs import enqueue_capture_processing_job
from app.services.capture_storage import source_file_content, source_file_url, upload_source_capture
from app.services.captures import assign_capture_patient, capture_metadata, delete_capture, get_capture, update_capture
from app.storage import ObjectStore, get_object_store

captures_api = APIRouter(prefix="/api/v1")


@captures_api.post("/captures")
async def upload_capture(
    capture_type: str = Form(...),
    session_id: str | None = Form(default=None),
    new_session: bool = Form(default=False),
    patient_id: str | None = Form(default=None),
    client_capture_id: str = Form(...),
    detail: str = Form(default=""),
    metadata: str | None = Form(default=None),
    file: UploadFile = File(...),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    """Upload a capture source file and attach it to a new or existing session."""
    metadata_payload = parse_metadata_form(metadata)
    return await upload_source_capture(
        db,
        object_store=object_store,
        principal=principal,
        capture_type_text=capture_type,
        session_id=None if new_session else session_id,
        patient_id=patient_id,
        client_capture_id=client_capture_id,
        detail=detail,
        file=file,
        metadata=metadata_payload,
    )


@captures_api.post("/sessions/{session_id}/captures")
async def upload_session_capture(
    session_id: str,
    capture_type: str = Form(...),
    patient_id: str | None = Form(default=None),
    client_capture_id: str = Form(...),
    detail: str = Form(default=""),
    metadata: str | None = Form(default=None),
    file: UploadFile = File(...),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    """Upload a capture source file directly into a specific session."""
    metadata_payload = parse_metadata_form(metadata)
    return await upload_source_capture(
        db,
        object_store=object_store,
        principal=principal,
        capture_type_text=capture_type,
        session_id=session_id,
        patient_id=patient_id,
        client_capture_id=client_capture_id,
        detail=detail,
        file=file,
        metadata=metadata_payload,
    )


@captures_api.get("/captures/{capture_id}")
def get_capture_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one capture and its processing metadata."""
    return get_capture(db, principal, capture_id)


@captures_api.patch("/captures/{capture_id}")
def update_capture_route(
    capture_id: str,
    request: CaptureUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable capture state or metadata."""
    return update_capture(db, principal, capture_id, request)


@captures_api.delete("/captures/{capture_id}")
def delete_capture_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Soft-delete a capture and return the updated session contract."""
    return delete_capture(db, principal, capture_id)


@captures_api.post("/captures/{capture_id}/assign-patient")
def assign_capture_patient_route(
    capture_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assign or clear the patient associated with a single capture."""
    return assign_capture_patient(db, principal, capture_id, request)


@captures_api.get("/captures/{capture_id}/file")
def get_capture_file_url(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    """Return a temporary object-storage URL for a capture source file."""
    return source_file_url(db, object_store=object_store, principal=principal, capture_id=capture_id)


@captures_api.get("/captures/{capture_id}/file-content")
def get_capture_file_content(
    capture_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """Stream capture source file bytes through the backend with range support."""
    file_content = source_file_content(db, object_store=object_store, principal=principal, capture_id=capture_id)
    return ranged_file_response(
        content=file_content["content"],
        media_type=file_content["media_type"],
        filename=file_content["filename"],
        range_header=range_header,
    )


@captures_api.post("/captures/{capture_id}/retry-processing")
def retry_capture_processing_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Queue a new AI processing job for a capture."""
    return enqueue_capture_processing_job(db, principal=principal, capture_id=capture_id)


@captures_api.get("/captures/{capture_id}/metadata")
def get_capture_metadata_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return capture metadata, including generated transcript or caption data."""
    return capture_metadata(db, principal, capture_id)
