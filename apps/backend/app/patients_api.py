"""Patient routes: search, duplicate guard, memory, last-visit/session context, CRUD.

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/patients``, ``patient_memory``, ``patient_matching``, ``patient_search``, and
``last_visit``.

Route order matters: the literal ``/patients/search`` and ``/patients/duplicate-check`` are
declared before the ``/patients/{patient_id}`` parameterized route so the literals win.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.schemas.patients import (
    DuplicateCheckRequest,
    PatientMemoryDetailResponse,
    PatientMemoryListResponse,
    PatientPatch,
    PatientWrite,
)
from app.services.last_visit import get_last_visit, get_session_context
from app.services.patient_matching import find_patient_duplicates
from app.services.patient_memory import get_patient_memory_detail, list_patient_memory
from app.services.patient_search import smart_search_patients
from app.services.patients import create_patient, get_patient, patient_payload, search_patients, update_patient

patients_api = APIRouter(prefix="/api/v1")


@patients_api.get("/patients")
def patients_search(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Search tenant patients by name, contact detail, or identifier."""
    return search_patients(db, principal, query, limit)


@patients_api.get("/patient-memory", response_model=PatientMemoryListResponse)
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


@patients_api.post("/patients")
def patients_create(
    request: PatientWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a patient record and its searchable identifiers."""
    return create_patient(db, principal, request)


@patients_api.get("/patients/search")
def patients_smart_search(
    query: str | None = Query(default=None, alias="q"),
    limit: int = Query(default=20, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deterministic, Persian-aware, multi-field, ranked patient search (AES-204)."""
    return smart_search_patients(db, principal, query=query, limit=limit)


@patients_api.post("/patients/duplicate-check")
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


@patients_api.get("/patients/{patient_id}")
def patients_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one patient record in the current tenant."""
    return patient_payload(get_patient(db, principal.tenant_id, patient_id))


@patients_api.get("/patients/{patient_id}/last-visit")
def patients_last_visit(
    patient_id: str,
    exclude_session_id: str | None = Query(default=None, alias="excludeSessionId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the patient's prior visit's note + before/after media (AES-106/203)."""
    return get_last_visit(db, principal, patient_id, exclude_session_id=exclude_session_id)


@patients_api.get("/patients/{patient_id}/session-context")
def patients_session_context(
    patient_id: str,
    exclude_session_id: str | None = Query(default=None, alias="excludeSessionId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deterministic session context (last-visit digest + recent-visits photo strip + key facts)."""
    return get_session_context(db, principal, patient_id, exclude_session_id=exclude_session_id)


@patients_api.get("/patients/{patient_id}/memory", response_model=PatientMemoryDetailResponse)
def patients_memory_get(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return patient memory summary and sortable timeline sessions."""
    return get_patient_memory_detail(db, principal, patient_id)


@patients_api.patch("/patients/{patient_id}")
def patients_update(
    patient_id: str,
    request: PatientPatch,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable patient demographics and identifiers."""
    return update_patient(db, principal, patient_id, request)
