"""Clinic team routes: the worklist line-up picker (/clinic/members) + team management (/clinic/team*).

A self-contained router mounted by ``main.py``. Handlers stay thin — team-management logic lives in
``app/services/team``; the active-members listing (for the worklist picker) lives in
``app/services/worklist``.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, tenant_admin_required
from app.db.session import get_db
from app.schemas.auth import MemberCreateRequest, MemberUpdateRequest
from app.services.team import create_team_member, list_team_members, update_team_member
from app.services.worklist import list_clinic_members

team_api = APIRouter(prefix="/api/v1")


@team_api.get("/clinic/members")
def clinic_members_route(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List the clinic's active staff members (for the worklist line-up picker; AES-903)."""
    return list_clinic_members(db, principal)


@team_api.get("/clinic/team")
def team_list_route(
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """List all clinic members (any status) for the Team management screen (owner/admin only)."""
    return list_team_members(db, principal)


@team_api.post("/clinic/team", status_code=201)
def team_create_route(
    request: MemberCreateRequest,
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Add a clinic member (creates the user + active membership) with a temp password (owner/admin)."""
    return create_team_member(
        db, principal, full_name=request.fullName, email=request.email, password=request.password, role=request.role
    )


@team_api.patch("/clinic/team/{user_id}")
def team_update_route(
    user_id: str,
    request: MemberUpdateRequest,
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Change a member's role and/or status (owner/admin; the owner + your own row are protected)."""
    return update_team_member(db, principal, user_id=user_id, role=request.role, status_value=request.status)
