import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Patient, PatientIdentifier, PatientStatus
from app.schemas.api import PatientPatch, PatientWrite
from app.services.patient_identity import (
    DETERMINISTIC_PATIENT_IDENTIFIER_TYPES,
    deterministic_identifier_specs,
    deterministic_identifier_specs_for_patient,
    normalize_identifier,
    normalize_national_id,
    normalized_aliases_for_value,
    search_keys_for_query,
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dateOfBirth") from exc


def patient_payload(patient: Patient) -> dict[str, Any]:
    national_id = next(
        (
            identifier.identifier_value
            for identifier in patient.identifiers
            if identifier.identifier_type == "national_id"
        ),
        None,
    )
    return {
        "id": str(patient.id),
        "tenantId": str(patient.tenant_id),
        "displayName": patient.display_name,
        "legalFirstName": patient.legal_first_name,
        "legalLastName": patient.legal_last_name,
        "nationalId": national_id,
        "dateOfBirth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex": patient.sex,
        "phone": patient.phone,
        "email": patient.email,
        "notes": patient.notes,
        "status": patient.status.value,
        "createdAt": patient.created_at.isoformat() if patient.created_at else None,
        "updatedAt": patient.updated_at.isoformat() if patient.updated_at else None,
    }


def get_patient(db: DbSession, tenant_id: uuid.UUID, patient_id: str) -> Patient:
    try:
        parsed = uuid.UUID(patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid patient_id") from exc
    patient = db.execute(
        select(Patient).where(Patient.id == parsed, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _current_national_id(patient: Patient) -> str | None:
    return next(
        (
            identifier.identifier_value
            for identifier in patient.identifiers
            if identifier.identifier_type == "national_id"
        ),
        None,
    )


def search_patients(db: DbSession, principal: CurrentPrincipal, query: str | None, limit: int = 50) -> list[dict[str, Any]]:
    from app.services.caseload import caseload_patient_condition

    statement = select(Patient).where(Patient.tenant_id == principal.tenant_id)
    # Federated caseloads (therapy): a clinician only searches their own clients (no-op elsewhere).
    caseload = caseload_patient_condition(db, principal)
    if caseload is not None:
        statement = statement.where(caseload)
    if query:
        pattern = f"%{query.strip()}%"
        search_keys = search_keys_for_query(query) or [normalize_identifier(query)]
        identifier_filters = [
            PatientIdentifier.normalized_value.ilike(f"%{search_key}%")
            for search_key in search_keys
            if search_key
        ]
        identifier_patient_ids = select(PatientIdentifier.patient_id).where(
            PatientIdentifier.tenant_id == principal.tenant_id,
            or_(*identifier_filters) if identifier_filters else PatientIdentifier.id.is_(None),
        )
        statement = statement.where(
            or_(
                Patient.display_name.ilike(pattern),
                Patient.legal_first_name.ilike(pattern),
                Patient.legal_last_name.ilike(pattern),
                Patient.phone.ilike(pattern),
                Patient.email.ilike(pattern),
                Patient.id.in_(identifier_patient_ids),
            )
        )
    patients = db.execute(statement.order_by(Patient.updated_at.desc()).limit(min(limit, 100))).scalars()
    return [patient_payload(patient) for patient in patients]


def replace_deterministic_patient_identifiers(
    db: DbSession,
    *,
    patient: Patient,
    national_id: str | None,
    source: str = "staff",
) -> None:
    """Refresh generated search identifiers while preserving non-deterministic aliases."""
    db.execute(
        delete(PatientIdentifier).where(
            PatientIdentifier.tenant_id == patient.tenant_id,
            PatientIdentifier.patient_id == patient.id,
            PatientIdentifier.identifier_type.in_(DETERMINISTIC_PATIENT_IDENTIFIER_TYPES),
            PatientIdentifier.source == source,
        )
    )
    for spec in deterministic_identifier_specs_for_patient(patient, national_id=national_id, source=source):
        db.add(PatientIdentifier(tenant_id=patient.tenant_id, patient_id=patient.id, **spec))


def _patient_information_text(patient_information: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = patient_information.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _patient_information_aliases(patient_information: dict[str, Any]) -> list[str]:
    values = [
        _patient_information_text(patient_information, "raw_mentioned_name"),
        _patient_information_text(patient_information, "standardized_display_name"),
    ]
    alternates = patient_information.get("alternate_transliterations")
    if isinstance(alternates, list):
        values.extend(value.strip() for value in alternates if isinstance(value, str) and value.strip())
    return list(dict.fromkeys(value for value in values if value))


def display_name_from_patient_information(patient_information: dict[str, Any]) -> str | None:
    """Return the best staff-facing name from generated identity data."""
    return _patient_information_text(patient_information, "raw_mentioned_name", "standardized_display_name", "full_name", "display_name")


def patient_information_has_createable_identity(patient_information: dict[str, Any]) -> bool:
    """Return whether generated identity is specific enough to create a patient."""
    return bool(
        display_name_from_patient_information(patient_information)
        or _patient_information_text(patient_information, "national_id", "phone", "email")
    )


def patient_information_has_explicit_identity(patient_information: dict[str, Any]) -> bool:
    """Return whether identity was explicitly extracted, not merely inferred from context."""
    return bool(_patient_information_text(patient_information, "raw_mentioned_name", "national_id", "phone", "email"))


def add_patient_information_identifiers(
    db: DbSession,
    *,
    patient: Patient,
    patient_information: dict[str, Any],
    source: str = "ai-engine",
) -> None:
    """Add AI-origin search identifiers from extracted patient information."""
    national_id = _patient_information_text(patient_information, "national_id")
    phone = _patient_information_text(patient_information, "phone")
    email = _patient_information_text(patient_information, "email")
    date_of_birth = _patient_information_text(patient_information, "date_of_birth")
    for spec in deterministic_identifier_specs(
        display_name=patient.display_name,
        legal_first_name=patient.legal_first_name,
        legal_last_name=patient.legal_last_name,
        national_id=national_id,
        date_of_birth=date_of_birth,
        phone=phone,
        email=email,
        source=source,
    ):
        db.add(PatientIdentifier(tenant_id=patient.tenant_id, patient_id=patient.id, **spec))

    seen: set[tuple[str, str]] = set()
    for value in _patient_information_aliases(patient_information):
        for alias in normalized_aliases_for_value(value):
            key = ("normalized_alias", alias)
            if key in seen:
                continue
            seen.add(key)
            db.add(
                PatientIdentifier(
                    tenant_id=patient.tenant_id,
                    patient_id=patient.id,
                    identifier_type="normalized_alias",
                    identifier_value=value,
                    normalized_value=alias,
                    source=source,
                    confidence=0.92,
                    identifier_metadata={
                        "generated_by": "ai-patient-creation",
                        "version": "2026-06-02",
                        "kind": "extracted_name_alias",
                    },
                )
            )


# System breadcrumb stamped on AI-created patients (a "finish setting this up" reminder, not a
# clinical fact). Surfaces that show patient "key facts" filter it out so it never reads as guidance.
AI_CREATED_PATIENT_NOTE = "Created by AI from an audio capture. Complete and verify patient details."


def create_patient_from_patient_information(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    patient_information: dict[str, Any],
    source_capture_id: uuid.UUID | None = None,
) -> Patient | None:
    """Create an active patient from generated identity data when no match exists."""
    display_name = display_name_from_patient_information(patient_information)
    if not patient_information_has_createable_identity(patient_information) or not display_name:
        return None

    patient = Patient(
        tenant_id=tenant_id,
        display_name=display_name,
        phone=_patient_information_text(patient_information, "phone"),
        email=_patient_information_text(patient_information, "email"),
        notes=AI_CREATED_PATIENT_NOTE,
        status=PatientStatus.active,
        created_by_user_id=created_by_user_id,
    )
    db.add(patient)
    db.flush()
    add_patient_information_identifiers(db, patient=patient, patient_information=patient_information)
    audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=created_by_user_id,
        action="patient.create_ai",
        target_type="patient",
        target_id=patient.id,
        details={
            "source_capture_id": str(source_capture_id) if source_capture_id else None,
            "patient_information": patient_information,
        },
    )
    return patient


def _refresh_patient_for_payload(db: DbSession, patient: Patient) -> None:
    db.refresh(patient)
    db.expire(patient, ["identifiers"])


def create_patient(db: DbSession, principal: CurrentPrincipal, request: PatientWrite) -> dict[str, Any]:
    """Create a patient, returning an existing exact match for safe retries."""
    if request.national_id:
        existing_by_identifier = db.execute(
            select(Patient)
            .join(PatientIdentifier, PatientIdentifier.patient_id == Patient.id)
            .where(
                Patient.tenant_id == principal.tenant_id,
                PatientIdentifier.tenant_id == principal.tenant_id,
                PatientIdentifier.identifier_type == "national_id",
                PatientIdentifier.normalized_value == normalize_national_id(request.national_id),
            )
        ).scalars().first()
        if existing_by_identifier is not None:
            return patient_payload(existing_by_identifier)

    existing_by_name = db.execute(
        select(Patient)
        .where(
            Patient.tenant_id == principal.tenant_id,
            Patient.display_name.ilike(request.display_name.strip()),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_by_name is not None:
        return patient_payload(existing_by_name)

    patient = Patient(
        tenant_id=principal.tenant_id,
        display_name=request.display_name,
        legal_first_name=request.legal_first_name,
        legal_last_name=request.legal_last_name,
        date_of_birth=parse_date(request.date_of_birth),
        sex=request.sex,
        phone=request.phone,
        email=request.email,
        notes=request.notes,
        status=PatientStatus.active,
        created_by_user_id=principal.user_id,
    )
    db.add(patient)
    db.flush()
    replace_deterministic_patient_identifiers(db, patient=patient, national_id=request.national_id)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="patient.create",
        target_type="patient",
        target_id=patient.id,
        details={},
    )
    db.commit()
    _refresh_patient_for_payload(db, patient)
    return patient_payload(patient)


def update_patient(db: DbSession, principal: CurrentPrincipal, patient_id: str, request: PatientPatch) -> dict[str, Any]:
    patient = get_patient(db, principal.tenant_id, patient_id)
    previous = patient_payload(patient)
    updates = request.model_dump(exclude_unset=True)
    next_national_id = _current_national_id(patient)
    if "display_name" in updates and request.display_name is not None:
        patient.display_name = request.display_name
    if "legal_first_name" in updates:
        patient.legal_first_name = request.legal_first_name
    if "legal_last_name" in updates:
        patient.legal_last_name = request.legal_last_name
    if "national_id" in updates:
        next_national_id = request.national_id
    if "date_of_birth" in updates:
        patient.date_of_birth = parse_date(request.date_of_birth)
    if "sex" in updates:
        patient.sex = request.sex
    if "phone" in updates:
        patient.phone = request.phone
    if "email" in updates:
        patient.email = request.email
    if "notes" in updates:
        patient.notes = request.notes
    if any(
        field in updates
        for field in ("display_name", "legal_first_name", "legal_last_name", "national_id", "date_of_birth", "phone", "email")
    ):
        db.flush()
        replace_deterministic_patient_identifiers(db, patient=patient, national_id=next_national_id)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="patient.update",
        target_type="patient",
        target_id=patient.id,
        details={"previous": previous},
    )
    db.commit()
    _refresh_patient_for_payload(db, patient)
    return patient_payload(patient)
