"""Federated caseloads (Spine A, therapy vertical) — foundation §7.

Multi-seat behavior differs by vertical:

- **aesthetics = shared workspace** — any provider sees any patient; the patient base is the
  clinic's. No caseload scoping (this module is a no-op there).
- **therapy = federated private caseloads** — a client belongs to *their* therapist; clients and
  their clinical content are private between clinicians by default. A therapist sees their **own**
  caseload: clients they created, or clients they have a session with.

This is a confidentiality wall, not RBAC — it scopes *which clients/sessions a clinician sees*, by
ownership, only in federated (therapy) tenants. It never blocks capture-first (the capturer owns
what they create, so it is always in their own caseload).
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Patient, Session, Tenant
from app.services.verticals import normalize_vertical

# Verticals whose multi-seat model is federated private caseloads (vs. a shared workspace).
FEDERATED_CASELOAD_VERTICALS = frozenset({"therapy"})


def tenant_vertical(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return a tenant's normalized vertical ('aesthetics' default; 'therapy', ...)."""
    value = db.execute(select(Tenant.vertical).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return normalize_vertical(value)


def is_federated_caseload(db: DbSession, tenant_id: uuid.UUID) -> bool:
    """True when this tenant scopes clients to the owning clinician (therapy), not a shared base."""
    return tenant_vertical(db, tenant_id) in FEDERATED_CASELOAD_VERTICALS


def caseload_patient_condition(db: DbSession, principal: CurrentPrincipal):
    """Return a SQLAlchemy condition restricting ``Patient`` rows to the principal's caseload.

    Returns ``None`` in a shared-workspace tenant (aesthetics) — apply nothing. In a federated
    (therapy) tenant, a client is in-caseload when the principal **created** the client or **owns a
    session** with the client.
    """
    if not is_federated_caseload(db, principal.tenant_id):
        return None
    owned_session_patient_ids = select(Session.patient_id).where(
        Session.tenant_id == principal.tenant_id,
        Session.created_by_user_id == principal.user_id,
        Session.patient_id.is_not(None),
    )
    return or_(
        Patient.created_by_user_id == principal.user_id,
        Patient.id.in_(owned_session_patient_ids),
    )


def patient_in_caseload(db: DbSession, principal: CurrentPrincipal, patient: Patient) -> bool:
    """Whether a specific patient is within the principal's caseload (always True if not federated)."""
    if not is_federated_caseload(db, principal.tenant_id):
        return True
    if patient.created_by_user_id == principal.user_id:
        return True
    owns_session = db.execute(
        select(Session.id)
        .where(
            Session.tenant_id == principal.tenant_id,
            Session.patient_id == patient.id,
            Session.created_by_user_id == principal.user_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    return owns_session is not None
