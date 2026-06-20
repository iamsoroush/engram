import json
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import CurrentPrincipal, get_current_principal, staff_or_admin_required, staff_required
from app.auth.service import dev_login, login, logout, me_response, refresh, update_tenant_settings
from app.config import settings
from app.observability import init_sentry, instrument
from app.observability.metrics import record_ai_job
from app.db.session import get_db
from app.schemas.api import (
    AftercareTemplatePatch,
    AftercareTemplateWrite,
    AiJobCompleteRequest,
    AiJobErrorRequest,
    AiJobProgressRequest,
    AiJobStartRequest,
    AiModelConfigUpdate,
    AssignPatientRequest,
    CaptureUpdate,
    DuplicateCheckRequest,
    PatientPatch,
    PatientMemoryDetailResponse,
    PatientMemoryListResponse,
    PatientShareCreate,
    PatientWrite,
    SessionCreate,
    SessionSaveRequest,
    SessionUpdate,
    TherapyFormatRequest,
    TherapyReflectionsRequest,
    TherapyReleaseRequest,
    TherapyRiskRequest,
    WorklistEntryCreate,
    WorklistEntryResolve,
)
from app.schemas.auth import DevLoginRequest, LoginRequest, LogoutRequest, RefreshRequest, TenantSettingsUpdate
from app.services.ai_model_config import ai_model_settings_payload, set_ai_model_overrides
from app.services.ai_jobs import (
    complete_worker_job,
    enqueue_capture_processing_job,
    fail_worker_job,
    get_ai_job,
    recover_all_ai_jobs,
    recover_ai_jobs,
    require_ai_engine_token,
    retry_worker_job,
    start_worker_job,
    sweep_stale_patient_memory,
    progress_worker_job,
)
from app.services.captures import assign_capture_patient, capture_metadata, delete_capture, get_capture, update_capture
from app.services.capture_storage import (
    internal_source_file_content,
    source_file_content,
    source_file_url,
    upload_source_capture,
)
from app.services.patients import create_patient, get_patient, patient_payload, search_patients, update_patient
from app.services.patient_memory import get_patient_memory_detail, list_patient_memory
from app.services.patient_matching import find_patient_duplicates
from app.services.patient_search import smart_search_patients
from app.services.assignment_suggestions import suggest_session_assignment
from app.services.last_visit import get_last_visit
from app.services.aftercare_templates import (
    aftercare_template_payload,
    create_aftercare_template,
    delete_aftercare_template,
    get_aftercare_template,
    list_aftercare_templates,
    update_aftercare_template,
)
from app.services.patient_surface import (
    create_patient_share,
    get_patient_share_payload,
    list_patient_shares,
    public_share_media,
    public_share_payload,
    revoke_patient_share,
)
from app.services.therapy_reporting import (
    update_therapy_format,
    update_therapy_reflections,
    update_therapy_release,
    update_therapy_risk,
)
from app.services.sessions import (
    assign_session_patient,
    create_session,
    get_session,
    list_session_artifacts,
    list_session_captures,
    list_session_ai_jobs,
    list_sessions,
    save_session,
    start_review,
    update_session,
)
from app.services.worklist import (
    create_worklist_entry,
    list_clinic_members,
    list_worklist,
    resolve_worklist_entry,
)
from app.storage import ObjectStore, get_object_store
from sqlalchemy.orm import Session

API_V1_PREFIX = "/api/v1"

# Error tracking is initialized once, before the app is built, so any startup-time errors are
# captured. No-op when BACKEND_SENTRY_DSN is empty (dev / Basic / unconfigured envs unaffected).
init_sentry()

app = FastAPI(
    title=settings.app_name,
    docs_url=f"{API_V1_PREFIX}/docs",
    redoc_url=f"{API_V1_PREFIX}/redoc",
    openapi_url=f"{API_V1_PREFIX}/openapi.json",
)

# Prometheus instrumentation: exposes /metrics (NOT under /api/v1) for the internal-network scrape.
instrument(app)

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


@internal_api.post("/ai/jobs/recover")
def internal_ai_jobs_recover(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Recover queued/retryable failed AI jobs and sweep stale Pro patient memory.

    The Celery-beat recovery task drives this. Besides re-dispatching durable jobs, it runs the
    patient-memory quiescence sweep (idle ~30 min + stale → refresh) — the background half of the
    decoupled memory trigger model, reusing the existing beat so no new infra is added.
    """
    result = recover_all_ai_jobs(db)
    result["memorySweep"] = sweep_stale_patient_memory(db)
    return result


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
    result = complete_worker_job(db, job_id=job_id, output_key=request.output_key, output=request.output)
    # AI-job outcome metric (notari_ai_jobs_total): completion is always a terminal success.
    record_ai_job("succeeded")
    return result


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
        retry_reason=request.retry_reason,
    )


@internal_api.post("/ai/jobs/{job_id}/fail")
def internal_ai_job_fail(
    job_id: str,
    request: AiJobErrorRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record terminal AI processing failure after retries are exhausted."""
    result = fail_worker_job(
        db,
        job_id=job_id,
        error_message=request.error_message,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
        retry_reason=request.retry_reason,
    )
    # AI-job outcome metric (notari_ai_jobs_total): count a failure only when the job is now
    # terminal. fail_worker_job may instead schedule a durable retry (status stays failed but
    # retryable) — that is a transient attempt, not a terminal failure, so it must not inflate the
    # failure rate the AIJobFailureRate alert watches.
    job_view = result.get("job", {}) if isinstance(result, dict) else {}
    metadata = job_view.get("resultMetadata") or {}
    is_terminal = job_view.get("status") == "failed" and metadata.get("retryable") is False
    if is_terminal:
        record_ai_job("failed")
    return result


@internal_api.get("/captures/{capture_id}/file-content")
def internal_capture_file_content(
    capture_id: str,
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """Stream capture source bytes to trusted internal AI processors."""
    file_content = internal_source_file_content(db, object_store=object_store, capture_id=capture_id)
    return Response(
        content=file_content["content"],
        media_type=file_content["media_type"],
        headers={"Content-Disposition": f'inline; filename="{file_content["filename"]}"'},
    )


@api_v1.post("/auth/dev-login")
def auth_dev_login(request: DevLoginRequest, db: Session = Depends(get_db)) -> Any:
    """Create a development authentication session for a demo persona."""
    return dev_login(db, request.persona, request.tier)


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


@api_v1.patch("/tenant/settings")
def update_tenant_settings_route(
    request: TenantSettingsUpdate,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Update tenant language preferences (transcription / report)."""
    return update_tenant_settings(db, principal, provided=request.model_dump(exclude_unset=True))


@api_v1.get("/ai-config/models")
def get_ai_models_route(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Return the live per-task AI model selection (blank model = worker env default)."""
    return ai_model_settings_payload(db)


@api_v1.put("/ai-config/models")
def update_ai_models_route(
    request: AiModelConfigUpdate,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Set per-task AI model overrides. Takes effect on the next AI request (no restart)."""
    set_ai_model_overrides(db, request.models, user_id=principal.user_id)
    return ai_model_settings_payload(db)


@api_v1.get("/patients")
def patients_search(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Search tenant patients by name, contact detail, or identifier."""
    return search_patients(db, principal, query, limit)


@api_v1.get("/patient-memory", response_model=PatientMemoryListResponse)
def patient_memory_list_route(
    query: str | None = Query(default=None),
    filter: str = Query(default="recent", pattern="^(recent|active|all|needs-input)$"),
    clinician_id: str | None = Query(default=None, alias="clinicianId"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List flat patient memory rows without nested session payloads."""
    return list_patient_memory(
        db,
        principal,
        query=query,
        memory_filter=filter,
        clinician_id=clinician_id,
        limit=limit,
        offset=offset,
    )


@api_v1.post("/patients")
def patients_create(
    request: PatientWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a patient record and its searchable identifiers."""
    return create_patient(db, principal, request)


@api_v1.get("/patients/search")
def patients_smart_search(
    query: str | None = Query(default=None, alias="q"),
    limit: int = Query(default=20, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deterministic, Persian-aware, multi-field, ranked patient search (AES-204)."""
    return smart_search_patients(db, principal, query=query, limit=limit)


@api_v1.post("/patients/duplicate-check")
def patients_duplicate_check(
    request: DuplicateCheckRequest,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Warn about likely existing patients before a duplicate is created (AES-205)."""
    return find_patient_duplicates(
        db,
        tenant_id=principal.tenant_id,
        display_name=request.display_name,
        national_id=request.national_id,
        phone=request.phone,
        email=request.email,
    )


@api_v1.get("/patients/{patient_id}")
def patients_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one patient record in the current tenant."""
    return patient_payload(get_patient(db, principal.tenant_id, patient_id))


@api_v1.get("/patients/{patient_id}/last-visit")
def patients_last_visit(
    patient_id: str,
    exclude_session_id: str | None = Query(default=None, alias="excludeSessionId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the patient's prior visit's note + before/after media (AES-106/203)."""
    return get_last_visit(db, principal, patient_id, exclude_session_id=exclude_session_id)


@api_v1.get("/patients/{patient_id}/memory", response_model=PatientMemoryDetailResponse)
def patients_memory_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return patient memory summary and sortable timeline sessions."""
    return get_patient_memory_detail(db, principal, patient_id)


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
    clinician_id: str | None = Query(default=None, alias="clinicianId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List sessions in the current tenant, optionally filtered by status or owning clinician.

    Pass ``clinicianId`` (e.g. the caller's own id) for the AES-904 "Mine" view; omit for "Clinic".
    """
    return list_sessions(db, principal, status, limit, clinician_id)


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


@api_v1.get("/sessions/{session_id}/assignment-suggestion")
def session_assignment_suggestion_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a deterministic, rule-based 'Assign to …?' suggestion for an unassigned visit (AES-301)."""
    return suggest_session_assignment(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/start-review")
def start_review_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Move an organized session into human review."""
    return start_review(db, principal, session_id)


@api_v1.post("/sessions/{session_id}/therapy/format")
def therapy_set_format_route(
    session_id: str,
    request: TherapyFormatRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Switch the therapy shareable-plane note format (DAP/SOAP/BIRP); re-projects the same content."""
    return update_therapy_format(db, principal, session_id, request.format)


@api_v1.post("/sessions/{session_id}/therapy/release")
def therapy_release_route(
    session_id: str,
    request: TherapyReleaseRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Explicitly release (or withdraw) the shareable summary to the client — a deliberate act."""
    return update_therapy_release(db, principal, session_id, request.released)


@api_v1.post("/sessions/{session_id}/therapy/risk")
def therapy_risk_route(
    session_id: str,
    request: TherapyRiskRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Clinician-confirm (or clear) a dated risk flag; assisted detection only suggests."""
    return update_therapy_risk(db, principal, session_id, active=request.active, level=request.level, note=request.note)


@api_v1.post("/sessions/{session_id}/therapy/reflections")
def therapy_reflections_route(
    session_id: str,
    request: TherapyReflectionsRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save the private-plane reflections (therapist-only; never exported)."""
    return update_therapy_reflections(db, principal, session_id, request.reflections)


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


@api_v1.post("/ai-jobs/recover")
def recover_ai_jobs_route(
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Requeue queued or retryable failed AI jobs after worker recovery."""
    return recover_ai_jobs(db, principal, limit)


@api_v1.get("/ai-jobs/{job_id}")
def get_ai_job_route(
    job_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one AI processing job and its current lifecycle state."""
    return get_ai_job(db, principal, job_id)


@api_v1.get("/clinic/members")
def clinic_members_route(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List the clinic's active staff members (for the worklist line-up picker; AES-903)."""
    return list_clinic_members(db, principal)


@api_v1.get("/worklist")
def list_worklist_route(
    scope: str = Query(default="mine", pattern="^(mine|clinic)$"),
    status: str = Query(default="waiting", pattern="^(waiting|seen|cancelled|all)$"),
    clinician_id: str | None = Query(default=None, alias="clinicianId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """A clinician's "Today / up next" worklist (AES-903). Default: the caller's waiting entries."""
    return list_worklist(db, principal, scope=scope, status_filter=status, clinician_id=clinician_id)


@api_v1.post("/worklist")
def create_worklist_route(
    request: WorklistEntryCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Line a patient up for a clinician (AES-903). A soft lane — capture-first is never blocked."""
    return create_worklist_entry(
        db,
        principal,
        patient_id=request.patient_id,
        clinician_user_id=request.clinician_user_id,
        note=request.note,
    )


@api_v1.post("/worklist/{entry_id}/seen")
def worklist_entry_seen_route(
    entry_id: str,
    request: WorklistEntryResolve | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Clear a worklist entry as seen, optionally linking the session the clinician started."""
    body = request or WorklistEntryResolve()
    return resolve_worklist_entry(db, principal, entry_id, new_status="seen", session_id=body.session_id)


@api_v1.delete("/worklist/{entry_id}")
def cancel_worklist_entry_route(
    entry_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel (remove) a worklist entry that no longer applies."""
    return resolve_worklist_entry(db, principal, entry_id, new_status="cancelled")


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


@api_v1.get("/aftercare-templates")
def aftercare_templates_list_route(
    procedure_type: str | None = Query(default=None, alias="procedureType"),
    include_inactive: bool = Query(default=False, alias="includeInactive"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the tenant's aftercare templates (AES-702)."""
    return list_aftercare_templates(db, principal, procedure_type=procedure_type, include_inactive=include_inactive)


@api_v1.post("/aftercare-templates")
def aftercare_templates_create_route(
    request: AftercareTemplateWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an aftercare template (AES-702)."""
    return create_aftercare_template(db, principal, request)


@api_v1.get("/aftercare-templates/{template_id}")
def aftercare_templates_get_route(
    template_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one aftercare template."""
    return aftercare_template_payload(get_aftercare_template(db, principal.tenant_id, template_id))


@api_v1.patch("/aftercare-templates/{template_id}")
def aftercare_templates_update_route(
    template_id: str,
    request: AftercareTemplatePatch,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update an aftercare template (AES-702)."""
    return update_aftercare_template(db, principal, template_id, request)


@api_v1.delete("/aftercare-templates/{template_id}")
def aftercare_templates_delete_route(
    template_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete an aftercare template."""
    return delete_aftercare_template(db, principal, template_id)


@api_v1.post("/patient-shares")
def patient_shares_create_route(
    request: PatientShareCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a tokenized, revocable share of curated content (AES-303/304/403)."""
    return create_patient_share(db, principal, request)


@api_v1.get("/patient-shares")
def patient_shares_list_route(
    patient_id: str | None = Query(default=None, alias="patientId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the tenant's patient shares, optionally scoped to one patient."""
    return list_patient_shares(db, principal, patient_id=patient_id)


@api_v1.get("/patient-shares/{share_id}")
def patient_shares_get_route(
    share_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one share with its curated preview (AES-403 per-share preview)."""
    return get_patient_share_payload(db, principal, share_id)


@api_v1.post("/patient-shares/{share_id}/revoke")
def patient_shares_revoke_route(
    share_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Revoke a share so its public link stops working (AES-403)."""
    return revoke_patient_share(db, principal, share_id)


@api_v1.get("/share/{token}")
def public_share_route(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PUBLIC, read-only: the patient's curated report + aftercare for a share token (AES-401)."""
    return public_share_payload(db, token)


@api_v1.get("/share/{token}/media/{capture_id}")
def public_share_media_route(
    token: str,
    capture_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """PUBLIC, read-only: stream a curated photo for a share (only if it is in the share)."""
    media = public_share_media(db, object_store=object_store, token=token, capture_id=capture_id)
    return ranged_file_response(
        content=media["content"],
        media_type=media["media_type"],
        filename=media["filename"],
        range_header=range_header,
    )


app.include_router(api_v1)
app.include_router(internal_api)
# Post-session patient Q&A (Pro payload of the patient surface; AES-402). Self-contained routers.
from app.qa_api import qa_api, qa_internal_api  # noqa: E402

app.include_router(qa_api)
app.include_router(qa_internal_api)
