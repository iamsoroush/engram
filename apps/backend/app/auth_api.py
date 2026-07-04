"""Authentication + current-user routes (/auth/*, /me).

A self-contained router mounted by ``main.py``; complements the ``app/auth/`` service package.
Handlers stay thin — all logic lives in ``app/auth/service.py``.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, get_current_principal
from app.auth.service import dev_login, login, logout, me_response, refresh, register, switch_tenant
from app.db.session import get_db
from app.schemas.auth import (
    DevLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SwitchTenantRequest,
)

auth_api = APIRouter(prefix="/api/v1")


@auth_api.post("/auth/dev-login")
def auth_dev_login(request: DevLoginRequest, db: Session = Depends(get_db)) -> Any:
    """Create a development authentication session for a demo persona."""
    return dev_login(db, request.persona, request.tier)


@auth_api.post("/auth/login")
def auth_login(request: LoginRequest, db: Session = Depends(get_db)) -> Any:
    """Authenticate with email and password and return access credentials."""
    return login(db, request.email, request.password, request.tenant_id)


@auth_api.post("/auth/register", status_code=201)
def auth_register(request: RegisterRequest, db: Session = Depends(get_db)) -> Any:
    """Self-serve clinic sign-up: create a tenant + its founding owner user and return credentials."""
    return register(
        db,
        clinic_name=request.clinicName,
        full_name=request.fullName,
        email=request.email,
        password=request.password,
        app_language=request.appLanguage,
    )


@auth_api.post("/auth/refresh")
def auth_refresh(request: RefreshRequest, db: Session = Depends(get_db)) -> Any:
    """Exchange a valid refresh token for a new access token."""
    return refresh(db, request.refresh_token)


@auth_api.post("/auth/switch-tenant")
def auth_switch_tenant(
    request: SwitchTenantRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Any:
    """Re-issue a session for another clinic the signed-in user belongs to (multi-clinic switch)."""
    return switch_tenant(db, principal, tenant_id=request.tenant_id)


@auth_api.post("/auth/logout")
def auth_logout(
    request: LogoutRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke a refresh token for the authenticated user."""
    logout(db, request.refresh_token, principal.user_id, principal.tenant_id)
    return {"status": "ok"}


@auth_api.get("/me")
def get_me(principal: CurrentPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)) -> Any:
    """Return the authenticated user, tenant, and membership context."""
    return me_response(db, principal.user, principal.tenant)
