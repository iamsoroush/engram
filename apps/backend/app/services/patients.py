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


def normalize_identifier(value: str) -> str:
    """Normalize identifiers for matching."""
    digits = "".join(character for character in value if character.isdigit())
    return digits or value.strip().lower()


def search_patients(db: DbSession, principal: CurrentPrincipal, query: str | None, limit: int = 50) -> list[dict[str, Any]]:
    statement = select(Patient).where(Patient.tenant_id == principal.tenant_id)
    if query:
        pattern = f"%{query.strip()}%"
        normalized_identifier = normalize_identifier(query)
        identifier_patient_ids = select(PatientIdentifier.patient_id).where(
            PatientIdentifier.tenant_id == principal.tenant_id,
            PatientIdentifier.normalized_value.ilike(f"%{normalized_identifier}%"),
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


def create_patient(db: DbSession, principal: CurrentPrincipal, request: PatientWrite) -> dict[str, Any]:
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
    for identifier_type, value in (
        ("national_id", request.national_id),
        ("phone", request.phone),
        ("email", request.email),
        ("normalized_name", request.display_name),
        ("birth_date", request.date_of_birth),
    ):
        if value:
            db.add(
                PatientIdentifier(
                    tenant_id=principal.tenant_id,
                    patient_id=patient.id,
                    identifier_type=identifier_type,
                    identifier_value=value,
                    normalized_value=normalize_identifier(value),
                    source="staff",
                    identifier_metadata={},
                )
            )
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
    db.refresh(patient)
    return patient_payload(patient)


def update_patient(db: DbSession, principal: CurrentPrincipal, patient_id: str, request: PatientPatch) -> dict[str, Any]:
    patient = get_patient(db, principal.tenant_id, patient_id)
    previous = patient_payload(patient)
    updates = request.model_dump(exclude_unset=True)
    if "display_name" in updates and request.display_name is not None:
        patient.display_name = request.display_name
    if "legal_first_name" in updates:
        patient.legal_first_name = request.legal_first_name
    if "legal_last_name" in updates:
        patient.legal_last_name = request.legal_last_name
    if "national_id" in updates:
        db.execute(
            delete(PatientIdentifier).where(
                PatientIdentifier.tenant_id == principal.tenant_id,
                PatientIdentifier.patient_id == patient.id,
                PatientIdentifier.identifier_type == "national_id",
            )
        )
        if request.national_id:
            db.add(
                PatientIdentifier(
                    tenant_id=principal.tenant_id,
                    patient_id=patient.id,
                    identifier_type="national_id",
                    identifier_value=request.national_id,
                    normalized_value=normalize_identifier(request.national_id),
                    source="staff",
                    identifier_metadata={},
                )
            )
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
    db.refresh(patient)
    return patient_payload(patient)
