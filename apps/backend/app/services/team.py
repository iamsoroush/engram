"""Clinic member management (launch gap A follow-up): the owner/admin Team screen.

Self-serve sign-up creates a solo ``owner``; this lets that owner (or an admin) add staff and manage
their role/status. MVP model: the owner creates the account directly with a temporary password they
hand over — no email/SMS invite delivery (that is the out-of-scope infra). The created member uses
the existing role + multi-seat permission-preset system; ``owner`` and ``patient`` are not assignable
here (the founder is the only owner; patients never reach staff surfaces).
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal
from app.auth.security import hash_password, utc_now
from app.auth.service import audit
from app.models import MembershipRole, MembershipStatus, TenantMembership, User, UserStatus

# Roles an owner/admin may assign to a member (owner = the founder only; patient = never staff).
CREATABLE_ROLES: frozenset[str] = frozenset({"doctor", "assistant", "admin"})
MEMBER_STATUSES: frozenset[str] = frozenset({"active", "disabled"})


def _member_payload(user: User, membership: TenantMembership, principal: CurrentPrincipal) -> dict[str, Any]:
    return {
        "userId": str(user.id),
        "displayName": user.full_name or user.email,
        "email": user.email,
        "role": membership.role.value,
        "status": membership.status.value,
        "isSelf": user.id == principal.user_id,
        "isOwner": membership.role == MembershipRole.owner,
    }


def list_team_members(db: Session, principal: CurrentPrincipal) -> dict[str, Any]:
    """All non-patient members of the tenant (any status) for the Team screen — owner first."""
    rows = db.execute(
        select(User, TenantMembership)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == principal.tenant_id,
            TenantMembership.role != MembershipRole.patient,
        )
        .order_by(TenantMembership.role != MembershipRole.owner, User.full_name, User.email)
    ).all()
    return {"items": [_member_payload(user, membership, principal) for user, membership in rows]}


def create_team_member(
    db: Session, principal: CurrentPrincipal, *, full_name: str, email: str, password: str | None, role: str
) -> dict[str, Any]:
    """Add a member to the caller's tenant.

    If ``email`` already belongs to a Engram user, that existing account is added to this clinic
    (cross-clinic membership) — their credentials are unchanged and ``password`` is ignored. Otherwise
    a brand-new user is created and ``password`` (a temporary one to hand over) is required.
    """
    role_value = role.strip().lower()
    if role_value not in CREATABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be doctor, assistant, or admin")
    normalized_email = email.strip().lower()
    existing_user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()

    if existing_user is not None:
        already = db.execute(
            select(TenantMembership.id).where(
                TenantMembership.tenant_id == principal.tenant_id,
                TenantMembership.user_id == existing_user.id,
            )
        ).scalar_one_or_none()
        if already is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This person is already a member of your clinic")
        user = existing_user
        created = False
    else:
        name = full_name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Member name is required")
        if not password or len(password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A temporary password of at least 8 characters is required for a new member",
            )
        user = User(email=normalized_email, full_name=name, password_hash=hash_password(password), status=UserStatus.active)
        db.add(user)
        db.flush()
        created = True

    membership = TenantMembership(
        tenant_id=principal.tenant_id,
        user_id=user.id,
        role=MembershipRole(role_value),
        status=MembershipStatus.active,
    )
    db.add(membership)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="clinic.member_create",
        target_type="user",
        target_id=user.id,
        details={"role": role_value, "existing_user": not created},
    )
    db.commit()
    return {**_member_payload(user, membership, principal), "created": created}


def update_team_member(
    db: Session, principal: CurrentPrincipal, *, user_id: str, role: str | None, status_value: str | None
) -> dict[str, Any]:
    """Change a member's role and/or status. Protects the owner and the caller's own membership."""
    try:
        target_user_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid member id") from exc

    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == principal.tenant_id,
            TenantMembership.user_id == target_user_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if membership.role == MembershipRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The clinic owner cannot be changed")
    if target_user_id == principal.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own membership")

    if role is not None:
        role_value = role.strip().lower()
        if role_value not in CREATABLE_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be doctor, assistant, or admin")
        membership.role = MembershipRole(role_value)
    if status_value is not None:
        status_clean = status_value.strip().lower()
        if status_clean not in MEMBER_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status must be active or disabled")
        membership.status = MembershipStatus(status_clean)

    membership.updated_at = utc_now()
    user = db.get(User, target_user_id)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="clinic.member_update",
        target_type="user",
        target_id=target_user_id,
        details={"role": membership.role.value, "status": membership.status.value},
    )
    db.commit()
    return _member_payload(user, membership, principal)
