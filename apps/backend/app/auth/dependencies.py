from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_jwt
from app.db.session import get_db
from app.models import Tenant, TenantStatus, User, UserStatus

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

    roles = frozenset(payload.get("roles") or [])
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant roles in token")
    return CurrentPrincipal(user=user, tenant=tenant, roles=roles, token_jti=payload["jti"])


def require_roles(*allowed_roles: str):
    def dependency(principal: CurrentPrincipal = Depends(get_current_principal)) -> CurrentPrincipal:
        if not principal.roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency


staff_required = require_roles("doctor", "assistant")
staff_or_admin_required = require_roles("doctor", "assistant", "admin")
