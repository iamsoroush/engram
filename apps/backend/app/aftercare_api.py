"""Aftercare-template routes (AES-702).

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/aftercare_templates``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.schemas.api import AftercareTemplatePatch, AftercareTemplateWrite
from app.services.aftercare_templates import (
    aftercare_template_payload,
    create_aftercare_template,
    delete_aftercare_template,
    get_aftercare_template,
    list_aftercare_templates,
    update_aftercare_template,
)

aftercare_api = APIRouter(prefix="/api/v1")


@aftercare_api.get("/aftercare-templates")
def aftercare_templates_list_route(
    procedure_type: str | None = Query(default=None, alias="procedureType"),
    include_inactive: bool = Query(default=False, alias="includeInactive"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the tenant's aftercare templates (AES-702)."""
    return list_aftercare_templates(db, principal, procedure_type=procedure_type, include_inactive=include_inactive)


@aftercare_api.post("/aftercare-templates")
def aftercare_templates_create_route(
    request: AftercareTemplateWrite,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an aftercare template (AES-702)."""
    return create_aftercare_template(db, principal, request)


@aftercare_api.get("/aftercare-templates/{template_id}")
def aftercare_templates_get_route(
    template_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one aftercare template."""
    return aftercare_template_payload(get_aftercare_template(db, principal.tenant_id, template_id))


@aftercare_api.patch("/aftercare-templates/{template_id}")
def aftercare_templates_update_route(
    template_id: str,
    request: AftercareTemplatePatch,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update an aftercare template (AES-702)."""
    return update_aftercare_template(db, principal, template_id, request)


@aftercare_api.delete("/aftercare-templates/{template_id}")
def aftercare_templates_delete_route(
    template_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete an aftercare template."""
    return delete_aftercare_template(db, principal, template_id)
