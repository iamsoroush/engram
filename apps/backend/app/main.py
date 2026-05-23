import json
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import CurrentPrincipal, get_current_principal, staff_or_admin_required, staff_required
from app.auth.service import dev_login, login, logout, me_response, refresh
from app.config import settings
from app.db.session import get_db
from app.schemas.api import (
    AiJobCompleteRequest,
    AiJobErrorRequest,
    AiJobProgressRequest,
    AiJobStartRequest,
    AssignPatientRequest,
    CaptureUpdate,
    PatientPatch,
    PatientWrite,
    SessionCreate,
    SessionSaveRequest,
    SessionUpdate,
)
from app.schemas.auth import DevLoginRequest, LoginRequest, LogoutRequest, RefreshRequest
from app.services.ai_jobs import (
    complete_worker_job,
    enqueue_capture_processing_job,
    fail_worker_job,
    get_ai_job,
    require_ai_engine_token,
    retry_worker_job,
    start_worker_job,
    progress_worker_job,
)
from app.services.captures import assign_capture_patient, capture_metadata, delete_capture, get_capture, update_capture
from app.services.capture_storage import (
    source_file_content,
    source_file_url,
    upload_source_capture,
)
from app.services.patients import create_patient, get_patient, patient_payload, search_patients, update_patient
from app.services.sessions import (
    assign_session_patient,
    create_session,
    get_session,
    list_session_artifacts,
    list_session_captures,
    list_session_ai_jobs,
    list_sessions,
    reopen_session,
    save_session,
    start_review,
    update_session,
    verify_session,
)
from app.storage import ObjectStore, get_object_store
from sqlalchemy.orm import Session

API_V1_PREFIX = "/api/v1"

app = FastAPI(
    title=settings.app_name,
    docs_url=f"{API_V1_PREFIX}/docs",
    redoc_url=f"{API_V1_PREFIX}/redoc",
    openapi_url=f"{API_V1_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix=API_V1_PREFIX)
internal_api = APIRouter(
    prefix="/internal",
    dependencies=[Depends(require_ai_engine_token)],
    include_in_schema=False,
)


def parse_metadata_form(metadata: str | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed


def ranged_file_response(content: bytes, media_type: str, filename: str, range_header: str | None = None) -> Response:
    """Return file content with byte-range support for mobile media playback."""
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    content_length = len(content)
    if not range_header:
        headers["Content-Length"] = str(content_length)
        return Response(content=content, media_type=media_type, headers=headers)

    unit, _, range_value = range_header.partition("=")
    start_text, _, end_text = range_value.partition("-")
    if unit != "bytes" or not start_text:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    try:
        start = int(start_text)
        end = int(end_text) if end_text else content_length - 1
    except ValueError:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    if start >= content_length or end < start:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    end = min(end, content_length - 1)
    partial = content[start : end + 1]
    headers["Content-Length"] = str(len(partial))
    headers["Content-Range"] = f"bytes {start}-{end}/{content_length}"
    return Response(content=partial, status_code=206, media_type=media_type, headers=headers)


@api_v1.get("/health")
def health_check() -> dict[str, str]:
    """Check whether the API process is running and able to serve requests."""
    return {"status": "ok"}


@internal_api.post("/ai/jobs/{job_id}/start")
def internal_ai_job_start(
    job_id: str,
    request: AiJobStartRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark an AI processing job as running and return worker input."""
    return start_worker_job(
        db,
        job_id=job_id,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
    )


@internal_api.post("/ai/jobs/{job_id}/complete")
def internal_ai_job_complete(
    job_id: str,
    request: AiJobCompleteRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist successful AI processing output from the worker."""
    return complete_worker_job(db, job_id=job_id, output_key=request.output_key, output=request.output)


@internal_api.post("/ai/jobs/{job_id}/progress")
def internal_ai_job_progress(
    job_id: str,
    request: AiJobProgressRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist partial AI processing output from the worker."""
    return progress_worker_job(db, job_id=job_id, output_key=request.output_key, output=request.output, stage=request.stage)


@internal_api.post("/ai/jobs/{job_id}/retry")
def internal_ai_job_retry(
    job_id: str,
    request: AiJobErrorRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a failed AI worker attempt before Celery retries the job."""
    return retry_worker_job(
        db,
        job_id=job_id,
        error_message=request.error_message,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
    )


@internal_api.post("/ai/jobs/{job_id}/fail")
def internal_ai_job_fail(
    job_id: str,
    request: AiJobErrorRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record terminal AI processing failure after retries are exhausted."""
    return fail_worker_job(
        db,
        job_id=job_id,
        error_message=request.error_message,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
    )


@api_v1.post("/auth/dev-login")
def auth_dev_login(request: DevLoginRequest, db: Session = Depends(get_db)) -> Any:
    """Create a development authentication session for a demo persona."""
    return dev_login(db, request.persona)


@api_v1.post("/auth/login")
def auth_login(request: LoginRequest, db: Session = Depends(get_db)) -> Any:
    """Authenticate with email and password and return access credentials."""
    return login(db, request.email, request.password, request.tenant_id)


@api_v1.post("/auth/refresh")
def auth_refresh(request: RefreshRequest, db: Session = Depends(get_db)) -> Any:
    """Exchange a valid refresh token for a new access token."""
    return refresh(db, request.refresh_token)


@api_v1.post("/auth/logout")
def auth_logout(
    request: LogoutRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke a refresh token for the authenticated user."""
    logout(db, request.refresh_token, principal.user_id, principal.tenant_id)
    return {"status": "ok"}


@api_v1.get("/me")
def get_me(principal: CurrentPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)) -> Any:
    """Return the authenticated user, tenant, and membership context."""
    return me_response(db, principal.user, principal.tenant)


@api_v1.get("/patients")
def patients_search(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Search tenant patients by name, contact detail, or identifier."""
    return search_patients(db, principal, query, limit)


@api_v1.post("/patients")
def patients_create(
    request: PatientWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a patient record and its searchable identifiers."""
    return create_patient(db, principal, request)


@api_v1.get("/patients/{patient_id}")
def patients_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one patient record in the current tenant."""
    return patient_payload(get_patient(db, principal.tenant_id, patient_id))


@api_v1.patch("/patients/{patient_id}")
def patients_update(
    patient_id: str,
    request: PatientPatch,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable patient demographics and identifiers."""
    return update_patient(db, principal, patient_id, request)


@api_v1.get("/sessions")
def get_sessions(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List sessions in the current tenant, optionally filtered by status."""
    return list_sessions(db, principal, status, limit)


@api_v1.post("/sessions")
def create_session_route(
    request: SessionCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an empty draft session for later captures."""
    return create_session(db, principal, request)


@api_v1.get("/sessions/{session_id}")
def get_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one session, including generated report fields when available."""
    return get_session(db, principal, session_id)


@api_v1.patch("/sessions/{session_id}")
def update_session_route(
    session_id: str,
    request: SessionUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable session fields such as title, summary, or status."""
    return update_session(db, principal, session_id, request)


@api_v1.post("/sessions/{session_id}/save")
def save_session_route(
    session_id: str,
    request: SessionSaveRequest | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save a draft session and queue session-level AI report processing."""
    return save_session(db, principal, session_id, request or SessionSaveRequest())


@api_v1.post("/sessions/{session_id}/retry-processing")
def retry_session_processing_route(
    session_id: str,
    request: SessionSaveRequest | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retry failed or reopened session-level AI report processing."""
    return save_session(db, principal, session_id, request or SessionSaveRequest())


@api_v1.post("/sessions/{session_id}/assign-patient")
def assign_session_patient_route(
    session_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assign or clear the patient associated with a session."""
    return assign_session_patient(db, principal, session_id, request)


@api_v1.post("/sessions/{session_id}/start-review")
def start_review_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Move an organized session into human review."""
    return start_review(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/verify")
def verify_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark a reviewed or organized session as clinically verified."""
    return verify_session(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/reopen")
def reopen_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reopen a verified session so it can be corrected or processed again."""
    return reopen_session(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/captures")
def list_session_captures_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all captures attached to a session."""
    return list_session_captures(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/artifacts")
def list_session_artifacts_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List stored source and generated artifacts attached to a session."""
    return list_session_artifacts(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/ai-jobs")
def list_session_ai_jobs_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List AI processing jobs associated with a session."""
    return list_session_ai_jobs(db, principal, session_id)


@api_v1.get("/ai-jobs/{job_id}")
def get_ai_job_route(
    job_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one AI processing job and its current lifecycle state."""
    return get_ai_job(db, principal, job_id)


@api_v1.post("/captures")
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


@api_v1.post("/sessions/{session_id}/captures")
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


@api_v1.get("/captures/{capture_id}")
def get_capture_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one capture and its processing metadata."""
    return get_capture(db, principal, capture_id)


@api_v1.patch("/captures/{capture_id}")
def update_capture_route(
    capture_id: str,
    request: CaptureUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable capture state or metadata."""
    return update_capture(db, principal, capture_id, request)


@api_v1.delete("/captures/{capture_id}")
def delete_capture_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Soft-delete a capture and return the updated session contract."""
    return delete_capture(db, principal, capture_id)


@api_v1.post("/captures/{capture_id}/assign-patient")
def assign_capture_patient_route(
    capture_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assign or clear the patient associated with a single capture."""
    return assign_capture_patient(db, principal, capture_id, request)


@api_v1.get("/captures/{capture_id}/file")
def get_capture_file_url(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    """Return a temporary object-storage URL for a capture source file."""
    return source_file_url(db, object_store=object_store, principal=principal, capture_id=capture_id)


@api_v1.get("/captures/{capture_id}/file-content")
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


@api_v1.post("/captures/{capture_id}/retry-processing")
def retry_capture_processing_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Queue a new AI processing job for a capture."""
    return enqueue_capture_processing_job(db, principal=principal, capture_id=capture_id)


@api_v1.get("/captures/{capture_id}/metadata")
def get_capture_metadata_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return capture metadata, including generated transcript or caption data."""
    return capture_metadata(db, principal, capture_id)


app.include_router(api_v1)
app.include_router(internal_api)
