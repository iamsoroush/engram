import re
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_jwt, decode_jwt, hash_password, hash_token, utc_now, verify_password
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
from app.services.permissions import CONFIGURABLE_ROLES, VALID_PRESETS, resolve_role_permissions
from app.services.verticals import encounter_label


def tenant_profile(tenant: Tenant) -> TenantProfile:
    """Build the client-facing tenant profile (shared by login / me / settings responses)."""
    return TenantProfile(
        id=str(tenant.id),
        name=tenant.name,
        tier=tenant.tier,
        transcriptionLanguage=tenant.transcription_language,
        reportLanguage=tenant.report_language,
        appLanguage=tenant.app_language,
        matchStrictness=tenant.match_strictness,
        shareIncludeBrands=tenant.share_include_brands,
        highRiskClinic=tenant.high_risk_clinic,
        vertical=tenant.vertical,
        encounterLabel=encounter_label(tenant.vertical),
        rolePermissions=resolve_role_permissions(tenant.role_permissions),
    )

DEV_NAMESPACE = uuid.UUID("43e7c2ca-b3a2-40a1-a1c8-a0f64a1d2c22")
DEV_TENANT_ID = uuid.uuid5(DEV_NAMESPACE, "tenant:demo")
# A second dev tenant on the Basic tier so Pro and Basic can be exercised side-by-side
# (dev-login `tier` selects which one). Mirrors production, where tier is a tenant attribute.
DEV_TENANT_BASIC_ID = uuid.uuid5(DEV_NAMESPACE, "tenant:demo-basic")
# A therapy dev tenant (single plan, vertical = therapy) so the therapy vertical's note-first
# capture, two-plane synthesis, and federated caseloads are testable end-to-end.
DEV_TENANT_THERAPY_ID = uuid.uuid5(DEV_NAMESPACE, "tenant:demo-therapy")
DEV_TENANTS = {
    "pro": {"id": DEV_TENANT_ID, "name": "Engram Demo Clinic", "slug": "engram-demo", "tier": "pro", "vertical": "aesthetics"},
    "basic": {"id": DEV_TENANT_BASIC_ID, "name": "Engram Demo Clinic (Basic)", "slug": "engram-demo-basic", "tier": "basic", "vertical": "aesthetics"},
    "therapy": {"id": DEV_TENANT_THERAPY_ID, "name": "Engram Therapy Demo", "slug": "engram-demo-therapy", "tier": "pro", "vertical": "therapy"},
}

DEV_PERSONAS = {
    "doctor": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:doctor"),
        "email": "doctor@engram.local",
        "full_name": "Dr. Demo",
        "role": MembershipRole.doctor,
    },
    "assistant": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:assistant"),
        "email": "assistant@engram.local",
        "full_name": "Ari Assistant",
        "role": MembershipRole.assistant,
    },
    "admin": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:admin"),
        "email": "admin@engram.local",
        "full_name": "Engram Admin",
        "role": MembershipRole.admin,
    },
    "therapist-b": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:therapist-b"),
        "email": "therapist-b@engram.local",
        "full_name": "Dr. Rava (Therapist B)",
        "role": MembershipRole.doctor,
    },
    "patient-preview": {
        "id": uuid.uuid5(DEV_NAMESPACE, "user:patient-preview"),
        "email": "patient@engram.local",
        "full_name": "Patient Preview",
        "role": MembershipRole.patient,
    },
}


def ensure_dev_seed(db: Session) -> None:
    for spec in DEV_TENANTS.values():
        if db.get(Tenant, spec["id"]) is None:
            db.add(
                Tenant(
                    id=spec["id"],
                    name=spec["name"],
                    slug=spec["slug"],
                    status=TenantStatus.active,
                    tier=spec["tier"],
                    vertical=spec["vertical"],
                )
            )

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

        for spec in DEV_TENANTS.values():
            membership = db.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == spec["id"],
                    TenantMembership.user_id == data["id"],
                )
            ).scalar_one_or_none()
            if membership is None:
                db.add(
                    TenantMembership(
                        tenant_id=spec["id"],
                        user_id=data["id"],
                        role=data["role"],
                        status=MembershipStatus.active,
                    )
                )
            else:
                membership.role = data["role"]
                membership.status = MembershipStatus.active

    # Each tenant gets its own distinct demo patient so it's obvious which tier you're in.
    _ensure_dev_patient(db, tenant_id=DEV_TENANT_ID, key="patient:sara-n", display_name="Sara N.", first="Sara", last="N.", phone="+1 555 0100")
    _ensure_dev_patient(db, tenant_id=DEV_TENANT_BASIC_ID, key="patient:basic-bita", display_name="Bita B.", first="Bita", last="B.", phone="+1 555 0200")
    _ensure_therapy_caseload(db)
    db.commit()


def _ensure_therapy_caseload(db: Session) -> None:
    """Seed two therapy clients owned by *different* therapists so federated caseloads are visible.

    Maryam K. belongs to Dr. Demo (the `doctor` persona); Hassan R. belongs to Dr. Rava
    (`therapist-b`). Each clinician sees only their own client in the therapy tenant.
    """
    _ensure_dev_client(
        db,
        key="patient:therapy-maryam",
        display_name="Maryam K.",
        first="Maryam",
        last="K.",
        phone="+1 555 0300",
        owner_user_id=DEV_PERSONAS["doctor"]["id"],
    )
    _ensure_dev_client(
        db,
        key="patient:therapy-hassan",
        display_name="Hassan R.",
        first="Hassan",
        last="R.",
        phone="+1 555 0400",
        owner_user_id=DEV_PERSONAS["therapist-b"]["id"],
    )


def _ensure_dev_client(
    db: Session,
    *,
    key: str,
    display_name: str,
    first: str,
    last: str,
    phone: str,
    owner_user_id: uuid.UUID,
) -> None:
    """Seed one therapy client (by deterministic id) owned by a specific clinician, if absent."""
    patient_id = uuid.uuid5(DEV_NAMESPACE, key)
    if db.get(Patient, patient_id) is not None:
        return
    db.add(
        Patient(
            id=patient_id,
            tenant_id=DEV_TENANT_THERAPY_ID,
            display_name=display_name,
            legal_first_name=first,
            legal_last_name=last,
            status=PatientStatus.active,
            created_by_user_id=owner_user_id,
        )
    )
    db.add_all(
        [
            PatientIdentifier(tenant_id=DEV_TENANT_THERAPY_ID, patient_id=patient_id, **spec)
            for spec in deterministic_identifier_specs(
                display_name=display_name,
                legal_first_name=first,
                legal_last_name=last,
                phone=phone,
                source="dev-seed",
            )
        ]
    )


def _ensure_dev_patient(db: Session, *, tenant_id: uuid.UUID, key: str, display_name: str, first: str, last: str, phone: str) -> None:
    """Seed one deterministic demo patient into a dev tenant when it has none."""
    if db.execute(select(Patient.id).where(Patient.tenant_id == tenant_id).limit(1)).scalar_one_or_none() is not None:
        return
    patient_id = uuid.uuid5(DEV_NAMESPACE, key)
    db.add(
        Patient(
            id=patient_id,
            tenant_id=tenant_id,
            display_name=display_name,
            legal_first_name=first,
            legal_last_name=last,
            status=PatientStatus.active,
            created_by_user_id=DEV_PERSONAS["doctor"]["id"],
        )
    )
    db.add_all(
        [
            PatientIdentifier(tenant_id=tenant_id, patient_id=patient_id, **spec)
            for spec in deterministic_identifier_specs(
                display_name=display_name,
                legal_first_name=first,
                legal_last_name=last,
                phone=phone,
                source="dev-seed",
            )
        ]
    )


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


def _membership_profiles(memberships: list[TenantMembership]) -> list[MembershipProfile]:
    """Client-facing memberships incl. clinic name, so a multi-clinic user can switch between them."""
    return [
        MembershipProfile(tenantId=str(membership.tenant_id), role=membership.role.value, tenantName=membership.tenant.name)
        for membership in memberships
    ]


def profile_response(db: Session, user: User, tenant: Tenant, persona: str | None, tokens: tuple[str, str]) -> AuthResponse:
    memberships = active_memberships(db, user.id)
    return AuthResponse(
        accessToken=tokens[0],
        refreshToken=tokens[1],
        user=UserProfile(id=str(user.id), email=user.email, displayName=user.full_name, persona=persona),
        tenant=tenant_profile(tenant),
        memberships=_membership_profiles(memberships),
    )


def me_response(db: Session, user: User, tenant: Tenant, persona: str | None = None) -> MeResponse:
    memberships = active_memberships(db, user.id)
    return MeResponse(
        user=UserProfile(id=str(user.id), email=user.email, displayName=user.full_name, persona=persona),
        tenant=tenant_profile(tenant),
        memberships=_membership_profiles(memberships),
    )


TRANSCRIPTION_LANGUAGE_OPTIONS = {"auto", "fa", "en", "ar"}
REPORT_LANGUAGE_OPTIONS = {"fa", "en", "ar"}
APP_LANGUAGE_OPTIONS = {"fa", "en", "ar"}
MATCH_STRICTNESS_OPTIONS = {"strict", "balanced", "lenient"}


def update_tenant_settings(db: Session, principal: "CurrentPrincipal", *, provided: dict) -> TenantProfile:
    """Update a tenant's language + match-strictness preferences (only the keys provided)."""
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if "transcriptionLanguage" in provided:
        value = str(provided["transcriptionLanguage"] or "auto").strip().lower()
        if value not in TRANSCRIPTION_LANGUAGE_OPTIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported transcription language")
        tenant.transcription_language = value
    if "reportLanguage" in provided:
        raw = provided["reportLanguage"]
        value = str(raw).strip().lower() if raw is not None else ""
        if value and value not in REPORT_LANGUAGE_OPTIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report language")
        tenant.report_language = value or None
    if "appLanguage" in provided:
        value = str(provided["appLanguage"] or "en").strip().lower()
        if value not in APP_LANGUAGE_OPTIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported app language")
        tenant.app_language = value
    if "matchStrictness" in provided:
        value = str(provided["matchStrictness"] or "strict").strip().lower()
        if value not in MATCH_STRICTNESS_OPTIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported match strictness")
        tenant.match_strictness = value
    if "shareIncludeBrands" in provided:
        tenant.share_include_brands = bool(provided["shareIncludeBrands"])
    if "highRiskClinic" in provided:
        tenant.high_risk_clinic = bool(provided["highRiskClinic"])
    if "rolePermissions" in provided:
        # AES-905: admin-only — role permissions are the clinic's org policy, not a per-user pref.
        # The clinic ``owner`` (founder) administers the tenant too, so it shares this gate with admin.
        if not principal.roles & {"owner", "admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can change role permissions")
        # Merge the provided per-role presets over the stored map. Only configurable roles and valid
        # presets are accepted (400 otherwise) — admin/owner are always full and can't be set here.
        # Persisting the merged map keeps `resolve_role_permissions` the single source.
        incoming = provided["rolePermissions"] or {}
        if not isinstance(incoming, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid rolePermissions")
        stored = dict(tenant.role_permissions or {})
        for role, preset in incoming.items():
            if role not in CONFIGURABLE_ROLES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role '{role}' is not configurable")
            preset_value = str(preset or "").strip().lower()
            if preset_value not in VALID_PRESETS:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported permission preset")
            stored[role] = preset_value
        tenant.role_permissions = stored
    audit(
        db,
        tenant_id=tenant.id,
        actor_user_id=principal.user_id,
        action="tenant.update_settings",
        target_type="tenant",
        target_id=tenant.id,
        details={
            "transcription_language": tenant.transcription_language,
            "report_language": tenant.report_language,
            "app_language": tenant.app_language,
            "match_strictness": tenant.match_strictness,
            "share_include_brands": tenant.share_include_brands,
            "role_permissions": tenant.role_permissions,
        },
    )
    db.commit()
    db.refresh(tenant)
    return tenant_profile(tenant)


PLAN_TIERS = {"basic", "pro"}


def set_tenant_plan(db: Session, principal: "CurrentPrincipal", *, tier: str) -> TenantProfile:
    """Switch the tenant's plan/tier (basic | pro). Owner/admin only (gated at the route); no payment."""
    tier_value = str(tier or "").strip().lower()
    if tier_value not in PLAN_TIERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan must be basic or pro")
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.tier = tier_value
    audit(
        db,
        tenant_id=tenant.id,
        actor_user_id=principal.user_id,
        action="tenant.set_plan",
        target_type="tenant",
        target_id=tenant.id,
        details={"tier": tier_value},
    )
    db.commit()
    db.refresh(tenant)
    return tenant_profile(tenant)


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


def dev_login(db: Session, persona: str, tier: str = "pro") -> AuthResponse:
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dev login is disabled")
    ensure_dev_seed(db)
    data = DEV_PERSONAS[persona]
    tenant_spec = DEV_TENANTS.get(tier, DEV_TENANTS["pro"])
    user = db.get(User, data["id"])
    tenant = db.get(Tenant, tenant_spec["id"])
    if user is None or tenant is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Dev seed failed")
    tokens = issue_tokens(db, user, tenant.id)
    audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.dev_login", details={"persona": persona, "tier": tenant.tier})
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


def switch_tenant(db: Session, principal: "CurrentPrincipal", *, tenant_id: str) -> AuthResponse:
    """Re-issue a session for another tenant the current user is an active member of (clinic switch)."""
    try:
        target_id = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id") from exc
    user = principal.user
    if target_id not in {m.tenant_id for m in active_memberships(db, user.id)}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership for that clinic")
    tenant = db.get(Tenant, target_id)
    if tenant is None or tenant.status != TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clinic is not active")
    tokens = issue_tokens(db, user, target_id)
    audit(db, tenant_id=target_id, actor_user_id=user.id, action="auth.switch_tenant")
    db.commit()
    return profile_response(db, user, tenant, None, tokens)


# A pragmatic email shape check (the model stores plain strings; we avoid the email-validator dep).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# New self-serve clinics start on Basic (works without the AI synthesis gateway); tier is upgraded
# out-of-band and is read-only to the clinic.
DEFAULT_SIGNUP_TIER = "basic"


def _slugify(name: str) -> str:
    """A url-safe tenant slug from a clinic name; falls back to ``clinic`` (e.g. for Persian names)."""
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return base or "clinic"


def _unique_tenant_slug(db: Session, name: str) -> str:
    """A slug guaranteed unique against existing tenants (numeric suffix, then a hex suffix)."""
    base = _slugify(name)
    candidate = base
    suffix = 2
    while db.execute(select(Tenant.id).where(Tenant.slug == candidate)).scalar_one_or_none() is not None:
        if suffix > 1000:
            return f"{base}-{uuid.uuid4().hex[:8]}"
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def register(
    db: Session, *, clinic_name: str, full_name: str, email: str, password: str, app_language: str | None
) -> AuthResponse:
    """Onboard a clinic: create the tenant + its founding ``owner`` user, then issue session tokens.

    The owner is a full superset (captures + administers). Works in any auth mode — this is the real
    sign-up path and never depends on dev seeding.
    """
    normalized_email = email.strip().lower()
    clinic = clinic_name.strip()
    name = full_name.strip()
    if not _EMAIL_RE.match(normalized_email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid email address")
    if not clinic or not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clinic name and your name are required")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    if db.execute(select(User.id).where(User.email == normalized_email)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    language = (app_language or "fa").strip().lower()
    if language not in APP_LANGUAGE_OPTIONS:
        language = "fa"

    tenant = Tenant(
        name=clinic,
        slug=_unique_tenant_slug(db, clinic),
        status=TenantStatus.active,
        tier=DEFAULT_SIGNUP_TIER,
        vertical="aesthetics",
        app_language=language,
    )
    db.add(tenant)
    db.flush()  # assign tenant.id

    user = User(
        email=normalized_email,
        full_name=name,
        password_hash=hash_password(password),
        status=UserStatus.active,
        last_login_at=utc_now(),
    )
    db.add(user)
    db.flush()  # assign user.id

    db.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=MembershipRole.owner,
            status=MembershipStatus.active,
        )
    )
    db.flush()  # the membership must exist before issue_tokens reads roles

    tokens = issue_tokens(db, user, tenant.id)
    audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.register", details={"role": "owner"})
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
