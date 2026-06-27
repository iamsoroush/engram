from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_jwt
from app.db.session import get_db
from app.models import MembershipStatus, Tenant, TenantMembership, TenantStatus, User, UserStatus

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentPrincipal:
    user: User
    tenant: Tenant
    roles: frozenset[str]
    token_jti: str

    @property
    def user_id(self) -> UUID:
        return self.user.id

    @property
    def tenant_id(self) -> UUID:
        return self.tenant.id


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(credentials.credentials, "access")
    user = db.get(User, UUID(payload["sub"]))
    tenant = db.get(Tenant, UUID(payload["tenant_id"]))
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    if tenant is None or tenant.status != TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is not active")

    # Authorize from the LIVE membership, not the token's `roles` claim — so disabling a member or
    # changing their role takes effect on their next request, not only at access-token expiry.
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.status == MembershipStatus.active,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership for tenant")
    roles = frozenset({membership.role.value})
    return CurrentPrincipal(user=user, tenant=tenant, roles=roles, token_jti=payload["jti"])


def require_roles(*allowed_roles: str):
    def dependency(principal: CurrentPrincipal = Depends(get_current_principal)) -> CurrentPrincipal:
        if not principal.roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency


# ``owner`` (the clinic's founding user) is a full superset: it captures like staff AND administers
# like admin, so it is accepted by every staff/admin gate below.
staff_required = require_roles("owner", "doctor", "assistant")
staff_or_admin_required = require_roles("owner", "doctor", "assistant", "admin")
# Tenant administration (managing staff/members). Only the clinic owner + admins.
tenant_admin_required = require_roles("owner", "admin")
