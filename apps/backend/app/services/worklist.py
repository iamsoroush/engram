"""The multi-seat worklist — reception lines a patient up for a clinician (E9, AES-903).

A *soft* "Today / up next" lane, never a gate. Reception (or any staff) lines a patient up for a
clinician; that clinician sees them under "up next" and taps through to the patient (history +
before/after) to start a session. Capture-first is untouched: the capture footer always starts a
fresh session regardless of the worklist. This is a list, **not a scheduler** — entries carry no
time slot, only creation order (oldest = next up). See ``docs/ux/redesign-foundation.md`` §7.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import MembershipRole, MembershipStatus, Patient, TenantMembership, User, WorklistEntry
from app.services.attribution import attribution_payload
from app.services.sessions import parse_uuid

WAITING = "waiting"
SEEN = "seen"
CANCELLED = "cancelled"
_VALID_STATUSES = {WAITING, SEEN, CANCELLED}

# Roles a patient can be lined up for (clinical seats). Reception lines patients up *for* these.
_CLINICIAN_ROLES = {MembershipRole.doctor.value, MembershipRole.assistant.value, MembershipRole.admin.value}


def _require_active_member(db: DbSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TenantMembership:
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.status == MembershipStatus.active,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinician not found in this clinic")
    return membership


def worklist_entry_payload(db: DbSession, entry: WorklistEntry, *, patient: Patient | None = None) -> dict[str, Any]:
    """Serialize one worklist entry with patient + attribution context (camelCase)."""
    if patient is None:
        patient = db.get(Patient, entry.patient_id)
    return {
        "id": str(entry.id),
        "status": entry.status,
        "note": entry.note,
        "patientId": str(entry.patient_id),
        "patientName": patient.display_name if patient is not None else None,
        "clinicianUserId": str(entry.clinician_user_id),
        "clinician": attribution_payload(db, entry.clinician_user_id),
        # Who lined this patient up (AES-901 attribution on the worklist itself).
        "linedUpBy": attribution_payload(db, entry.created_by_user_id),
        "sessionId": str(entry.session_id) if entry.session_id else None,
        "createdAt": entry.created_at.isoformat() if entry.created_at else None,
        "updatedAt": entry.updated_at.isoformat() if entry.updated_at else None,
        "resolvedAt": entry.resolved_at.isoformat() if entry.resolved_at else None,
    }


def create_worklist_entry(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    patient_id: str,
    clinician_user_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Line a patient up for a clinician. Idempotent on (patient, clinician) while still waiting."""
    patient_uuid = parse_uuid(patient_id, "patient_id")
    clinician_uuid = parse_uuid(clinician_user_id, "clinician_user_id")
    patient = db.execute(
        select(Patient).where(Patient.id == patient_uuid, Patient.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    membership = _require_active_member(db, principal.tenant_id, clinician_uuid)
    if membership.role.value not in _CLINICIAN_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only line a patient up for a clinician")

    existing = db.execute(
        select(WorklistEntry).where(
            WorklistEntry.tenant_id == principal.tenant_id,
            WorklistEntry.patient_id == patient_uuid,
            WorklistEntry.clinician_user_id == clinician_uuid,
            WorklistEntry.status == WAITING,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Already lined up for this clinician — refresh the note rather than duplicate the row.
        if note is not None:
            existing.note = note
            db.commit()
            db.refresh(existing)
        return worklist_entry_payload(db, existing, patient=patient)

    entry = WorklistEntry(
        tenant_id=principal.tenant_id,
        patient_id=patient_uuid,
        clinician_user_id=clinician_uuid,
        status=WAITING,
        note=note,
        created_by_user_id=principal.user_id,
    )
    db.add(entry)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="worklist.line_up",
        target_type="worklist_entry",
        target_id=entry.id,
        details={"patient_id": str(patient_uuid), "clinician_user_id": str(clinician_uuid)},
    )
    db.commit()
    db.refresh(entry)
    return worklist_entry_payload(db, entry, patient=patient)


def list_worklist(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    scope: str = "mine",
    status_filter: str = WAITING,
    clinician_id: str | None = None,
) -> dict[str, Any]:
    """List worklist entries. ``scope`` "mine" → only the caller's; "clinic" → everyone's.

    ``clinician_id`` (if given) filters to that clinician and takes precedence over ``scope``.
    ``status_filter`` ∈ waiting | seen | cancelled | all (default waiting). Oldest first (next up).
    """
    if status_filter not in _VALID_STATUSES and status_filter != "all":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    statement = select(WorklistEntry).where(WorklistEntry.tenant_id == principal.tenant_id)
    target_clinician: uuid.UUID | None = None
    if clinician_id:
        target_clinician = parse_uuid(clinician_id, "clinician_id")
    elif scope == "mine":
        target_clinician = principal.user_id
    if target_clinician is not None:
        statement = statement.where(WorklistEntry.clinician_user_id == target_clinician)
    if status_filter != "all":
        statement = statement.where(WorklistEntry.status == status_filter)
    entries = db.execute(statement.order_by(WorklistEntry.created_at.asc())).scalars().all()
    patients = {
        patient.id: patient
        for patient in (
            db.execute(
                select(Patient).where(Patient.id.in_([entry.patient_id for entry in entries]))
            ).scalars()
            if entries
            else []
        )
    }
    return {
        "scope": "clinic" if (clinician_id is None and scope != "mine") else "mine",
        "clinicianId": str(target_clinician) if target_clinician is not None else None,
        "status": status_filter,
        "items": [worklist_entry_payload(db, entry, patient=patients.get(entry.patient_id)) for entry in entries],
    }


def resolve_worklist_entry(
    db: DbSession,
    principal: CurrentPrincipal,
    entry_id: str,
    *,
    new_status: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Mark an entry ``seen`` (optionally linking the started session) or ``cancelled``."""
    if new_status not in {SEEN, CANCELLED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    entry = db.execute(
        select(WorklistEntry).where(
            WorklistEntry.id == parse_uuid(entry_id, "entry_id"),
            WorklistEntry.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worklist entry not found")
    entry.status = new_status
    entry.resolved_at = datetime.now(timezone.utc)
    if session_id:
        entry.session_id = parse_uuid(session_id, "session_id")
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action=f"worklist.{new_status}",
        target_type="worklist_entry",
        target_id=entry.id,
        details={"session_id": str(entry.session_id) if entry.session_id else None},
    )
    db.commit()
    db.refresh(entry)
    return worklist_entry_payload(db, entry)


def list_clinic_members(db: DbSession, principal: CurrentPrincipal) -> dict[str, Any]:
    """Active staff members of the tenant (for the line-up picker + name resolution)."""
    rows = db.execute(
        select(User, TenantMembership.role)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == principal.tenant_id,
            TenantMembership.status == MembershipStatus.active,
            TenantMembership.role != MembershipRole.patient,
        )
        .order_by(User.full_name, User.email)
    ).all()
    return {
        "items": [
            {
                "userId": str(user.id),
                "displayName": user.full_name or user.email,
                "role": role.value,
                "isClinician": role.value in _CLINICIAN_ROLES,
            }
            for user, role in rows
        ]
    }
