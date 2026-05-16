import json
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import CurrentPrincipal, get_current_principal, staff_or_admin_required, staff_required
from app.auth.service import dev_login, login, logout, me_response, refresh
from app.config import settings
from app.db.session import get_db
from app.schemas.api import AssignPatientRequest, CaptureUpdate, PatientPatch, PatientWrite, SessionCreate, SessionUpdate
from app.schemas.auth import DevLoginRequest, LoginRequest, LogoutRequest, RefreshRequest
from app.services.captures import assign_capture_patient, capture_metadata, get_capture, update_capture
from app.services.capture_storage import (
    source_file_content,
    source_file_url,
    upload_source_capture,
)
from app.services.fake_processing import fake_organize_session, fake_process_capture, get_fake_job
from app.services.patients import create_patient, get_patient, patient_payload, search_patients, update_patient
from app.services.sessions import (
    assign_session_patient,
    create_session,
    get_session,
    list_session_artifacts,
    list_session_captures,
    list_session_fake_jobs,
    list_sessions,
    reopen_session,
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


@api_v1.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@api_v1.post("/auth/dev-login")
def auth_dev_login(request: DevLoginRequest, db: Session = Depends(get_db)) -> Any:
    return dev_login(db, request.persona)


@api_v1.post("/auth/login")
def auth_login(request: LoginRequest, db: Session = Depends(get_db)) -> Any:
    return login(db, request.email, request.password, request.tenant_id)


@api_v1.post("/auth/refresh")
def auth_refresh(request: RefreshRequest, db: Session = Depends(get_db)) -> Any:
    return refresh(db, request.refresh_token)


@api_v1.post("/auth/logout")
def auth_logout(
    request: LogoutRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    logout(db, request.refresh_token, principal.user_id, principal.tenant_id)
    return {"status": "ok"}


@api_v1.get("/me")
def get_me(principal: CurrentPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)) -> Any:
    return me_response(db, principal.user, principal.tenant)


@api_v1.get("/patients")
def patients_search(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return search_patients(db, principal, query, limit)


@api_v1.post("/patients")
def patients_create(
    request: PatientWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_patient(db, principal, request)


@api_v1.get("/patients/{patient_id}")
def patients_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return patient_payload(get_patient(db, principal.tenant_id, patient_id))


@api_v1.patch("/patients/{patient_id}")
def patients_update(
    patient_id: str,
    request: PatientPatch,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_patient(db, principal, patient_id, request)


@api_v1.get("/sessions")
def get_sessions(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_sessions(db, principal, status, limit)


@api_v1.post("/sessions")
def create_session_route(
    request: SessionCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_session(db, principal, request)


@api_v1.get("/sessions/{session_id}")
def get_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_session(db, principal, session_id)


@api_v1.patch("/sessions/{session_id}")
def update_session_route(
    session_id: str,
    request: SessionUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_session(db, principal, session_id, request)


@api_v1.post("/sessions/{session_id}/assign-patient")
def assign_session_patient_route(
    session_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return assign_session_patient(db, principal, session_id, request)


@api_v1.post("/sessions/{session_id}/start-review")
def start_review_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return start_review(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/verify")
def verify_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return verify_session(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/reopen")
def reopen_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return reopen_session(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/captures")
def list_session_captures_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_session_captures(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/artifacts")
def list_session_artifacts_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_session_artifacts(db, principal, session_id)


@api_v1.get("/sessions/{session_id}/fake-jobs")
def list_session_fake_jobs_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_session_fake_jobs(db, principal, session_id)


@api_v1.patch("/sessions/{session_id}/organize")
def organize_session(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    return fake_organize_session(db, object_store=object_store, principal=principal, session_id=session_id)


@api_v1.post("/sessions/{session_id}/fake-organize")
def fake_organize(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    return fake_organize_session(db, object_store=object_store, principal=principal, session_id=session_id)


@api_v1.get("/fake-jobs/{job_id}")
def get_fake_job_route(
    job_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_fake_job(db, principal, job_id)


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
    return get_capture(db, principal, capture_id)


@api_v1.patch("/captures/{capture_id}")
def update_capture_route(
    capture_id: str,
    request: CaptureUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_capture(db, principal, capture_id, request)


@api_v1.post("/captures/{capture_id}/assign-patient")
def assign_capture_patient_route(
    capture_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return assign_capture_patient(db, principal, capture_id, request)


@api_v1.get("/captures/{capture_id}/file")
def get_capture_file_url(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    return source_file_url(db, object_store=object_store, principal=principal, capture_id=capture_id)


@api_v1.get("/captures/{capture_id}/file-content")
def get_capture_file_content(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    file_content = source_file_content(db, object_store=object_store, principal=principal, capture_id=capture_id)
    return Response(
        content=file_content["content"],
        media_type=file_content["media_type"],
        headers={"Content-Disposition": f'inline; filename="{file_content["filename"]}"'},
    )


@api_v1.post("/captures/{capture_id}/fake-process")
def fake_process_capture_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    return fake_process_capture(db, object_store=object_store, principal=principal, capture_id=capture_id)


@api_v1.get("/captures/{capture_id}/metadata")
def get_capture_metadata_route(
    capture_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return capture_metadata(db, principal, capture_id)


app.include_router(api_v1)
