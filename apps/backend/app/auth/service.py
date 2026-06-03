import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_jwt, decode_jwt, hash_token, utc_now, verify_password
from app.config import settings
from app.models import (
    AuditEvent,
    AuthRefreshToken,
    MembershipRole,
    MembershipStatus,
    Patient,
    PatientIdentifier,
    PatientStatus,
    Tenant,
    TenantMembership,
    TenantStatus,
    User,
    UserStatus,
)
from app.schemas.auth import AuthResponse, MembershipProfile, MeResponse, RefreshResponse, TenantProfile, UserProfile
from app.services.patient_identity import deterministic_identifier_specs

DEV_NAMESPACE = uuid.UUID("43e7c2ca-b3a2-40a1-a1c8-a0f64a1d2c22")
DEV_TENANT_ID = uuid.uuid5(DEV_NAMESPACE, "tenant:demo")

DEV_PERSONAS = {
    "doctor": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:doctor"),
        "email": "doctor@aesmem.local",
        "full_name": "Dr. Demo",
        "role": MembershipRole.doctor,
    },
    "assistant": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:assistant"),
        "email": "assistant@aesmem.local",
        "full_name": "Ari Assistant",
        "role": MembershipRole.assistant,
    },
    "admin": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:admin"),
        "email": "admin@aesmem.local",
        "full_name": "AesMem Admin",
        "role": MembershipRole.admin,
    },
    "patient-preview": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:patient-preview"),
        "email": "patient@aesmem.local",
        "full_name": "Patient Preview",
        "role": MembershipRole.patient,
    },
}


def ensure_dev_seed(db: Session) -> None:
    tenant = db.get(Tenant, DEV_TENANT_ID)
    if tenant is None:
        tenant = Tenant(
            id=DEV_TENANT_ID,
            name="AesMem Demo Clinic",
            slug="aesmem-demo",
            status=TenantStatus.active,
            tier="pro",
        )
        db.add(tenant)

    for persona, data in DEV_PERSONAS.items():
        user = db.get(User, data["id"])
        if user is None:
            user = User(
                id=data["id"],
                email=data["email"],
                full_name=data["full_name"],
                auth_subject=f"dev:{persona}",
                status=UserStatus.active,
            )
            db.add(user)
        else:
            user.email = data["email"]
            user.full_name = data["full_name"]
            user.auth_subject = f"dev:{persona}"
            user.status = UserStatus.active

        membership = db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == DEV_TENANT_ID,
                TenantMembership.user_id == data["id"],
            )
        ).scalar_one_or_none()
        if membership is None:
            db.add(
                TenantMembership(
                    tenant_id=DEV_TENANT_ID,
                    user_id=data["id"],
                    role=data["role"],
                    status=MembershipStatus.active,
                )
            )
        else:
            membership.role = data["role"]
            membership.status = MembershipStatus.active

    if db.execute(select(Patient.id).where(Patient.tenant_id == DEV_TENANT_ID).limit(1)).scalar_one_or_none() is None:
        sample_patient_id = uuid.uuid5(DEV_NAMESPACE, "patient:sara-n")
        db.add(
            Patient(
                id=sample_patient_id,
                tenant_id=DEV_TENANT_ID,
                display_name="Sara N.",
                legal_first_name="Sara",
                legal_last_name="N.",
                status=PatientStatus.active,
                created_by_user_id=DEV_PERSONAS["doctor"]["id"],
            )
        )
        db.add_all(
            [
                PatientIdentifier(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=sample_patient_id,
                    **spec,
                )
                for spec in deterministic_identifier_specs(
                    display_name="Sara N.",
                    legal_first_name="Sara",
                    legal_last_name="N.",
                    phone="+1 555 0100",
                    source="dev-seed",
                )
            ]
        )

    db.commit()


def active_memberships(db: Session, user_id: uuid.UUID) -> list[TenantMembership]:
    return list(
        db.execute(
            select(TenantMembership)
            .where(TenantMembership.user_id == user_id, TenantMembership.status == MembershipStatus.active)
            .order_by(TenantMembership.created_at)
        ).scalars()
    )


def audit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str = "auth",
    target_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            details=details or {},
        )
    )


def roles_for_tenant(db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID) -> list[str]:
    return [
        membership.role.value
        for membership in db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == MembershipStatus.active,
            )
        ).scalars()
    ]


def profile_response(db: Session, user: User, tenant: Tenant, persona: str | None, tokens: tuple[str, str]) -> AuthResponse:
    memberships = active_memberships(db, user.id)
    return AuthResponse(
        accessToken=tokens[0],
        refreshToken=tokens[1],
        user=UserProfile(id=str(user.id), email=user.email, displayName=user.full_name, persona=persona),
        tenant=TenantProfile(id=str(tenant.id), name=tenant.name, tier=tenant.tier),
        memberships=[
            MembershipProfile(tenantId=str(membership.tenant_id), role=membership.role.value) for membership in memberships
        ],
    )


def me_response(db: Session, user: User, tenant: Tenant, persona: str | None = None) -> MeResponse:
    memberships = active_memberships(db, user.id)
    return MeResponse(
        user=UserProfile(id=str(user.id), email=user.email, displayName=user.full_name, persona=persona),
        tenant=TenantProfile(id=str(tenant.id), name=tenant.name, tier=tenant.tier),
        memberships=[
            MembershipProfile(tenantId=str(membership.tenant_id), role=membership.role.value) for membership in memberships
        ],
    )


def issue_tokens(db: Session, user: User, tenant_id: uuid.UUID) -> tuple[str, str]:
    roles = roles_for_tenant(db, user.id, tenant_id)
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership for tenant")

    access_token, _, _ = create_jwt(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=roles,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_minutes),
    )
    refresh_token, refresh_jti, refresh_expires_at = create_jwt(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=roles,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_days),
    )
    db.add(
        AuthRefreshToken(
            user_id=user.id,
            tenant_id=tenant_id,
            jti=refresh_jti,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
        )
    )
    return access_token, refresh_token


def dev_login(db: Session, persona: str) -> AuthResponse:
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dev login is disabled")
    ensure_dev_seed(db)
    data = DEV_PERSONAS[persona]
    user = db.get(User, data["id"])
    tenant = db.get(Tenant, DEV_TENANT_ID)
    if user is None or tenant is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Dev seed failed")
    tokens = issue_tokens(db, user, tenant.id)
    audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.dev_login", details={"persona": persona})
    db.commit()
    return profile_response(db, user, tenant, persona, tokens)


def login(db: Session, email: str, password: str, tenant_id: str | None) -> AuthResponse:
    user = db.execute(select(User).where(User.email == email, User.status == UserStatus.active)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    memberships = active_memberships(db, user.id)
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active tenant membership")

    try:
        selected_tenant_id = uuid.UUID(tenant_id) if tenant_id else memberships[0].tenant_id
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id") from exc
    if selected_tenant_id not in {membership.tenant_id for membership in memberships}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership for tenant")

    tenant = db.get(Tenant, selected_tenant_id)
    if tenant is None or tenant.status != TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is not active")

    user.last_login_at = utc_now()
    tokens = issue_tokens(db, user, tenant.id)
    audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.login")
    db.commit()
    return profile_response(db, user, tenant, None, tokens)


def refresh(db: Session, refresh_token: str) -> RefreshResponse:
    payload = decode_jwt(refresh_token, "refresh")
    jti = payload["jti"]
    token_row = db.execute(select(AuthRefreshToken).where(AuthRefreshToken.jti == jti)).scalar_one_or_none()
    if (
        token_row is None
        or token_row.revoked_at is not None
        or token_row.expires_at <= utc_now()
        or token_row.token_hash != hash_token(refresh_token)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, uuid.UUID(payload["sub"]))
    tenant = db.get(Tenant, uuid.UUID(payload["tenant_id"]))
    if user is None or user.status != UserStatus.active or tenant is None or tenant.status != TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token_row.revoked_at = utc_now()
    access_token, next_refresh_token = issue_tokens(db, user, tenant.id)
    audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.refresh")
    db.commit()
    return RefreshResponse(accessToken=access_token, refreshToken=next_refresh_token)


def logout(db: Session, refresh_token: str | None, user_id: uuid.UUID | None, tenant_id: uuid.UUID | None) -> None:
    actor_user_id = user_id
    audit_tenant_id = tenant_id
    if refresh_token:
        payload = decode_jwt(refresh_token, "refresh")
        token_row = db.execute(select(AuthRefreshToken).where(AuthRefreshToken.jti == payload["jti"])).scalar_one_or_none()
        if token_row is not None:
            token_row.revoked_at = utc_now()
            actor_user_id = token_row.user_id
            audit_tenant_id = token_row.tenant_id

    if audit_tenant_id is not None:
        audit(db, tenant_id=audit_tenant_id, actor_user_id=actor_user_id, action="auth.logout")
    db.commit()
